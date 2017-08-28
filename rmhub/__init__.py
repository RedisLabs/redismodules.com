import hashlib
import json
import logging
import os
import re
from datetime import datetime

from dotenv import find_dotenv, load_dotenv
from github import Github, InputGitTreeElement, enable_console_debug_logging, UnknownObjectException
from redis import ConnectionPool, Redis, StrictRedis
from redisearch import Client as RediSearchClient
from redisearch import (AutoCompleter, NumericField, Query, SortbyField,
                        Suggestion, TextField)
from rejson import Client as ReJSONClient
from rejson import Path
from rq import Queue
from rq_scheduler import Scheduler

from stopwords import stopwords

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(find_dotenv())

# TODO:
# * Interactions with gh fail on SSL, timeouts... - need to devise a way to deal w/ that

def _durationms(func, *args, **kwargs):
    start = datetime.now()
    res = func(*args, **kwargs)
    return res, (datetime.now() - start).total_seconds() * 1000.0

def _toepoch(ts):
    return (ts - datetime(1970,1,1)).total_seconds()

class Hub(object):
    dconn = None   # document store connection
    sconn = None   # search index connection
    qconn = None   # queue connection
    gh = None
    autocomplete = None
    repo = None
    _ts = None
    _hubkey = 'hub:catalog'
    _ixname = 'ix'
    _acname = 'ac'

    def __init__(self, ghlogin_or_token=None, docs_url=None, search_url=None, queue_url=None, repo=None):
        timestamp = datetime.utcnow()
        logger.info('Initializing temporary hub {}'.format(timestamp))

        if ghlogin_or_token:
            self.gh = Github(ghlogin_or_token)
        elif 'GITHUB_TOKEN' in os.environ:
            self.gh = Github(os.environ['GITHUB_TOKEN'])
        else:
            logger.info('Env var ''GITHUB_TOKEN'' not found')

        if docs_url:
            pass
        elif 'DOCS_REDIS_URL' in os.environ:
            docs_url = os.environ['DOCS_REDIS_URL']
        else:
            logger.critical('No Redis for document storage... bye bye.')
            raise RuntimeError('No Redis for document storage... bye bye.')
        self.dconn = ReJSONClient().from_url(docs_url)

        if search_url:
            pass
        elif 'SEARCH_REDIS_URL' in os.environ:
            search_url = os.environ['SEARCH_REDIS_URL']
        else:
            search_url = docs_url
        conn = Redis(connection_pool=ConnectionPool().from_url(search_url))
        self.sconn = RediSearchClient(self._ixname, conn=conn)
        self.autocomplete = AutoCompleter(self._acname, conn=conn)

        if queue_url:
            pass
        elif 'QUEUE_REDIS_URL' in os.environ:
            queue_url = os.environ['QUEUE_REDIS_URL']
        else:
            queue_url = docs_url
        self.qconn = StrictRedis.from_url(queue_url)

        if repo:
            pass
        elif 'REDISMODULES_REPO' in os.environ:
            repo = os.environ['REDISMODULES_REPO']
        else:
            logger.critical('No REDISMODULES_REPO... bye bye.')
            raise RuntimeError('No REDISMODULES_REPO... bye bye.')
        self.repo = repo

        # Check if hub exists
        if self.dconn.exists(self._hubkey):
            self._ts = datetime.fromtimestamp(float(self.dconn.jsonget(self._hubkey, Path('.created'))))
            logger.info('Latching to hub {}'.format(self._ts))
        else:
            self._ts = timestamp
            logger.info('Creating hub {}'.format(self._ts))
            self.createHub()
            self.addModulesRepo(self.repo)

    def get_repo_url(self):
        return 'https://github.com/{}'.format(self.repo)

    def createHub(self):
        logger.info('Creating the hub in the database {}'.format(self._ts))
        # Store the master modules catalog as an object
        self.dconn.jsonset(self._hubkey, Path.rootPath(),
        {
            'created': str(_toepoch(self._ts)),
            'modules': {},
            'submissions': [],
            'submit_enabled': False
        })

        # Create a RediSearch index for the modules
        # TODO: catch errors
        self.sconn.create_index((
            TextField('name', sortable=True),
            TextField('description'),
            NumericField('stargazers_count', sortable=True),
            NumericField('forks_count', sortable=True),
            NumericField('last_modified', sortable=True)
        ), stopwords=stopwords)

    def deleteHub(self):
        # TODO
        pass

    def addModule(self, mod):
        logger.info('Adding module to hub {}'.format(mod['name']))
        # Store the module object as a document
        m = RedisModule(self.dconn, self.sconn, self.autocomplete, mod['name'])
        m.save(mod)

        # Add a reference to it in the master catalog
        self.dconn.jsonset(self._hubkey, Path('.modules["{}"]'.format(m.get_id())), 
        {
            'id': m.get_id(),
            'key': m.get_key(),
            'created': str(_toepoch(self._ts)),
        })

        # Schedule a job to refresh repository statistics, starting from now and every hour
        s = Scheduler(connection=self.qconn)
        job = s.schedule(
            scheduled_time=datetime(1970,1,1),
            func=callRedisModuleUpateStats,
            args=[m.get_id()],
            interval=60*60,     # every hour
            repeat=None,        # indefinitely
            ttl=0,
            result_ttl=0
        )
        return m

    """
    Adds modules to the hub from a local directory
    TODO: deprecate asap
    """
    def addModulesPath(self, path):
        logger.info('Loading modules from local path {}'.format(path))
        # Iterate module JSON files
        for filename in os.listdir(path):
            if filename.endswith(".json"): 
                with open('{}/{}'.format(path, filename)) as fp:
                    mod = json.load(fp)

                m = self.addModule(mod['name'], mod)

    """
    Adds a modules to the hub from a github repository
    """
    def addModulesRepo(self, name, path='/modules/'):
        # TODO: check for success
        q = Queue(connection=self.qconn)
        q.enqueue(callLoadModulesFromRepo, name, path)

    def loadModulesFromRepo(self, name, path):
        logger.info('Loading modules from Github {} {}'.format(name, path))
        # TODO: error handling, sometimes not all contents are imported?
        repo = self.gh.get_repo(name)
        files = repo.get_dir_contents(path)
        for f in files:
            mod = json.loads(f.decoded_content)
            m = self.addModule(mod)

    """
    Submits a module to the hub
    """
    def submitModule(self, repo_id, **kwargs):
        logger.info('Module submitted to hub {}'.format(repo_id))
        repo_id = repo_id.lower()
        ts = datetime.utcnow()
        res = {
            'id': repo_id,
            'status': 'failed'
        }

        if not self.dconn.jsonget(self._hubkey, Path('submit_enabled')):
            res['message'] = 'Module submission is currently disabled'
            return res            

        # Check if the module is already listed
        m = RedisModule(self.dconn, self.sconn, self.autocomplete, repo_id)
        if m.exists:
            # TODO: return in search results
            res['message'] = 'Module already listed in the hub'
            return res

        # Check if there's an active submission, or if the failure was too recent
        submission = Submission(self.dconn, repo_id)
        if submission.exists:
            status = submission.status
            if status != 'failed':
                res['status'] = 'active'
                res['message'] = 'Active submission found for module'
                return res
            else:
                # TODO: handle failed submissions
                res['message'] = 'Module already submitted to the hub and had failed, please reset manually for now'
                return res

        # Store the new submission
        submission.save(**kwargs)

        # Record the submission in the catalog
        # TODO: find a good use for that, e.g. 5 last submissions
        self.dconn.jsonarrappend(self._hubkey, Path('.submissions'), {
            'id': submission.get_id(),
            'created': submission.created,
        })

        # Add a job to process the submission
        q = Queue(connection=self.qconn)
        job = q.enqueue(callProcessSubmission, submission.get_id())
        if job is None:
            res['message'] = 'Submission job could not be created'
            # TODO: design retry path
            logger.error('Could not create submission processing job for {}'.format(submission.get_id()))
        else:
            res['status'] = 'queued'
            submission.status = res['status']
            submission.job = job.id

        return res

    def viewSubmissionStatus(self, repo_id):
        submission = Submission(self.dconn, repo_id)
        if submission.exists:
            res = {
                'id': submission.get_id(),
                'status': submission.status,
                'message': submission.message,
            }
            if 'finished' == res['status']:
                res['pull_number'] = submission.pull_number
                res['pull_url'] = submission.pull_url
            return res

    def processSubmission(self, repo_id):
        logger.info('Processing submision for {}'.format(repo_id))
        submission = Submission(self.dconn, repo_id)
        if submission.exists:
            return submission.process(self.gh, self.repo)

    def viewModules(self, query=None, sort=None):
        if not query:
            # Use a purely negative query to get all modules
            query = '-etaoinshrdlu'
        q = Query(query).no_content().paging(0, 1000)
        if sort:
            if sort == 'update':
                q.sort_by('last_modified')
            elif sort == 'stars':
                q.sort_by('stargazers_count', asc=False)
            elif sort == 'forks':
                q.sort_by('forks_count', asc=False)
            elif sort == 'name':
                q.sort_by('name')

        results = self.sconn.search(q)
        mods = []
        fetch_duration = 0
        # TODO: this should be pipelined
        for doc in results.docs:
            m = RedisModule(self.dconn, self.sconn, self.autocomplete, doc.id)
            res, duration = _durationms(m.to_dict)
            mods.append(res)
            fetch_duration += duration

        return {
            'results': results.total,
            'search_duration': '{:.3f}'.format(results.duration),
            'fetch_duration': '{:.3f}'.format(fetch_duration),
            'total_duration': '{:.3f}'.format(fetch_duration + results.duration),
            'modules': mods,
        }

    def viewSearchSuggestions(self, prefix):
        suggestions = self.autocomplete.get_suggestions(prefix)
        return [s.string for s in suggestions]

class Repository(object):
    data = None
    def __init__(self, idof, typeof, url):
        self.data = {
            'id': idof,
            'type': typeof,
            'url': url
        }

    def get_id(self):
        return self.data['id']

    def get(self):
        return self.data

class GithubRepository(Repository):
    def __init__(self, idof):
        Repository.__init__(self, idof, 'github', 'https://github.com/{}'.format(idof))

class Author(object):
    data = None
    def __init__(self, idof, typeof, url):
        self.data = {
            'id': idof,
            'type': typeof,
            'url': url
        }

    def get_id(self):
        if self.data:
            return self.data['id']
        else:
            return None

    def get(self):
        return self.data

class GithubAuthor(Author):
    def __init__(self, idof=None):
        if idof:
            Author.__init__(self, idof, 'github', 'https://github.com/{}'.format(idof))

class ReJSONObject(object):
    _key = None
    _conn = None

    def __init__(self, conn, key):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_key', key)

    def __getattr__(self, name):
        path = Path(name)
        if self._conn.jsontype(self._key, path):
            return self._conn.jsonget(self._key, path)

    def __setattr__(self, name, value):
        return self._conn.jsonset(self._key, Path(name), value)

    def __delattr__(self, name):
        return self._conn.jsondel(self._key, Path(name))

    @property
    def exists(self):
        return self._conn.exists(self._key)

    def get_key(self):
        return self._key

    def to_dict(self):
        if self.exists:
            return self._conn.jsonget(self._key)

class Submission(ReJSONObject):
    _repo_id = None

    def __init__(self, conn, repo_id):
        object.__setattr__(self, '_repo_id', repo_id.lower())
        ReJSONObject.__init__(self, conn, 'submission:{}'.format(self._repo_id))

    def save(self, **kwargs):
        submission = {
            'created': _toepoch(datetime.utcnow()),
            'id': self._repo_id,
            'status': 'new',
            'message': 'Pending processing',
            'details': {
                'name': self._repo_id.split('/')[1],
                'repository': self._repo_id,
            }
        }
        if 'authors' in kwargs:
            submission['details']['authors'] = kwargs['authors']
        if 'docs_url' in kwargs:
            submission['details']['docs_url'] = kwargs['docs_url']
        if 'icon_url' in kwargs:
            submission['details']['icon_url'] = kwargs['icon_url']
        if 'certification' in kwargs:
            submission['certification'] = kwargs['certification']

        return self._conn.jsonset(self._key, Path.rootPath(), submission)

    def get_id(self):
        return self._repo_id

    def set_status(self, status, message):
        self.status = status
        self.message = message

    def process(self, gh, hubrepo):
        logger.info('Submission {} processing started'.format(self._repo_id))
        # TODO: should this be broken to littler steps?
        details = self.details

        try:
            # TODO: try to validate submission a litle more, e.g. README and LICENSE exist, other min reqs?
            self.set_status('started', 'Fetching repository')
            subrepo = gh.get_repo(self._repo_id)
            description = subrepo.description or 'This module has an air of mystery about it' 
        except UnknownObjectException:
            self.set_status('failed', 'Repository not found on Github')
            return

        # TODO: move this to using RedisModule class as template
        mod = {
            'name': details['name'],
            'license': None,
            'repository': {
                'type': 'github',
                'id': details['repository'],
                'url': 'https://github.com/{}'.format(details['repository'])
            },
            'documentation': self.docs_url,
            'description': description,
            'authors': []
        }

        # Validate authors
        # TODO: currenty only gh
        self.message = 'Validating authors'
        if authors in details:
            for author in details['authors']:
                try:
                    ghauthor = gh.get_user(author)
                except UnknownObjectException:
                    self.set_status('failed', 'Author {} not found on Github'.format(author))
                    return
                mod['authors'].append({
                    'type': 'github',
                    'id': author,
                    'url': 'https://github.com/{}'.format(author)
                })

        # TODO: validate and try to bring the icon from url and/or file upload
        if 'icon_url' in details and details['icon_url']:
            mod['icon'] = details['icon_url']

        # Submit to Github as a pull request
        ghrepo = gh.get_repo(hubrepo)
        ghdefault = ghrepo.get_branch(ghrepo.default_branch)

        # Get the branch for the submission
        try:
            ghsubref = ghrepo.get_git_ref('heads/submissions/{}'.format(mod['name']))
            self.message = 'Found existing submission reference'
        except UnknownObjectException:
            ghsubref = None

        # Create it if it doesn't exist
        if not ghsubref or not ghsubref.ref:
            self.message = 'Creating a branch for submission'
            ghsubref = ghrepo.create_git_ref('refs/heads/submissions/{}'.format(mod['name']), ghdefault.commit.sha)

        self.message = 'Creating commit tree'
        ghsub = ghrepo.get_branch('submissions/{}'.format(mod['name']))
        parent = ghrepo.get_git_commit(ghsub.commit.sha)

        # Create a new tree from the existing reference
        # TODO: add the icon if fetchable & suitable
        currtree = ghrepo.get_git_tree(ghsub.commit.sha)
        jsonfile = json.dumps(mod, indent=4, separators=(',', ': '))
        elems = [
            InputGitTreeElement('modules/{}.json'.format(mod['name']), '100644', 'blob', content=jsonfile),
        ]
        tree = ghrepo.create_git_tree(elems, base_tree=currtree)

        # Fetch the existing pull request, if it does
        self.message = 'Checking existing pull requests'
        pr = None
        for p in ghrepo.get_pulls(head=ghsub.name):
            # TODO: is it safe to assume 0 or 1?
            pr = p

        # Commit the tree
        self.message = 'Creating commit'
        if pr:
            message = 'Updates submission'
        else:
            message = 'Initial submission of module {}'.format(mod['name'])
        commit = ghrepo.create_git_commit(message, tree, [parent])
        self.commit = commit.sha

        # Update the submission's reference
        # TODO: resolve why this isn't a fast forward
        self.message = 'Updating branch reference'
        ghsubref.edit(commit.sha, force=True)

        # Create a PR if it doesn't exist already
        if not pr:
            self.message = 'Creating pull request'
            # Prepare the body of the pull request
            labels = [ 'submission' ]
            certification = self.certification
            body =  'This module has been submitted via the hub.\n\n'
            body += 'Owner: @{}\n'.format(subrepo.owner.login)
            if mod['authors']:
                body += 'Authors:'
                for author in mod['authors']:
                    body += ' @{}'.format(author['id'])
            if certification:
                body += '\n\nThe submitter had asked for the module to be certified.'
                labels.append('certification')

            # The pull request is created against the master branch
            prkw = {
                'title': '[SUBMISSION] {}'.format(mod['name']),
                'body': body,
                'head': ghsub.name,
                'base': ghdefault.name,
            }
            pr = ghrepo.create_pull(**prkw)

            # Set up labels for the pull's issue
            self.message = 'Setting labels'
            issue = ghrepo.get_issue(pr.number)
            issue.edit(labels=labels)

        self.status = 'finished'
        self.pull_number = pr.number
        self.pull_url = pr.html_url
        return pr.number

class RedisModule(ReJSONObject):
    _doc_id = None
    _autocomplete = None
    _sconn = None

    def __init__(self, dconn, sconn, autocomplete, doc_id):
        object.__setattr__(self, '_doc_id', doc_id.lower())
        object.__setattr__(self, '_autocomplete', autocomplete)
        object.__setattr__(self, '_sconn', sconn)
        ReJSONObject.__init__(self, dconn, 'module:{}'.format(self._doc_id))

    def get_id(self):
        return self._doc_id

    def save(self, mod):
        # Store the module
        self._conn.jsonset(self._key, Path.rootPath(), mod)

        # Index it
        self._sconn.add_document(self._doc_id, nosave=True,
            name=mod['name'],
            description=mod['description'], 
        )

        # Add the module's name and description to the suggestions engine
        text = '{} {}'.format(mod['name'], mod['description'])
        words = set(re.compile('\w+').findall(text))
        words = set(w.lower() for w in words)
        words = words.difference(stopwords)
        self._autocomplete.add_suggestions(*[Suggestion(w) for w in words])

    def updateStats(self, gh):
        # github.enable_console_debug_logging()
        repo = self.repository

        if repo and \
            'type' in repo and repo['type'] == 'github' and \
            'id' in repo:

            logger.info('Fetching stats for {}'.format(repo['id']))
            grepo = gh.get_repo(repo['id'])
            stats = {
                'stargazers_count': grepo.stargazers_count,
                'forks_count': grepo.forks_count,
                'last_modified': (datetime.today() - grepo.pushed_at).days  # TODO: take last push from default branch
            }

            rel = grepo.get_releases()
            try:
                stats['last_release'] = {
                    'name': rel[0].tag_name,
                    'url': rel[0].url
                }
            except IndexError:      # No releases
                pass

        self.stats = stats
        self._sconn.add_document(self._doc_id, nosave=True, replace=True, name=self.name, description=self.description, **stats)

"""
Exported Functions
"""

def callRedisModuleUpateStats(docId):
    logger.info('Calling update stats for {}'.format(docId))
    hub = Hub()
    if hub.gh:
        module = RedisModule(hub.dconn, hub.sconn, hub.autocomplete, docId)
        module.updateStats(hub.gh)
    else:
        logger.error('No Github access for updating stats {}'.format(docId))

def callLoadModulesFromRepo(name, path):
    logger.info('Calling load modules from github {} {}'.format(name, path))
    hub = Hub()
    if hub.gh:
        hub.loadModulesFromRepo(name, path)
    else:
        logger.error('No Github access for loading {} {}'.format(name, path))

def callProcessSubmission(repoid):
    logger.info('Calling process module submission {}'.format(repoid))
    hub = Hub()
    if hub.gh:
        hub.processSubmission(repoid)
    else:
        logger.error('No Github access for processing submission {}'.format(repoid))
