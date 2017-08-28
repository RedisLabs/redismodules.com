# Deploying


Setup:
Github token needs to have access to public repos
Repo needs to have 'submission' and 'certification' labels

## To AWS

### Prerequirements:
* `pip install awscli --upgrade`
* http://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_CLI_installation.html

* Also need to spin an ECS EC2 instance

```bash
ecs-cli configure --cluster rmhub --region us-east-1 --profile default
ecs-cli up --keypair itamar-rl-benchmarks3 --capability-iam --size 1 --instance-type t2.medium --port 8000
aws ecr create-repository --repository-name rmhub-redis --region us-east-1
# 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-redis
aws ecr create-repository --repository-name rmhub-app --region us-east-1
# 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-app
aws ecr create-repository --repository-name rmhub-web --region us-east-1
#726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-web

aws ecr get-login --no-include-email
<paste it>
docker build -t 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-app -f Dockerfile.app .
docker build -t 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-web -f Dockerfile.web .
docker build -t 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-redis -f Dockerfile.redis .

docker push 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-app:latest
docker push 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-web:latest
docker push 726902207197.dkr.ecr.us-east-1.amazonaws.com/rmhub-redis:latest


ecs-cli up --keypair itamar-rl-benchmarks3 --capability-iam --size 1 --instance-type m4.2xlarge
ecs-cli compose -f docker-compose-aws.yml up
```