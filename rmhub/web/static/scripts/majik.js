/* Handlebars helpers
* ------------------
*/
// Handlebars helper for stargazers badge
Handlebars.registerHelper("starsbadge", function(count) {
    var out = "";
    if (null != count) {
        out = out +
        "<div class=\"flex-badge-container\" data-toggle=\"tooltip\" title=\"Stargazers\">" +
        "<i class=\"octicon octicon-star\" aria-hidden=\"true\"></i>" +
        "<div class=\"repo-statum\">" +
        count +
        "</div></div>";
    }
    return new Handlebars.SafeString(out);
});

// Helper for forks badge
Handlebars.registerHelper("forksbadge", function(count) {
    var out = "";
    if (null != count) {
        out = out +
        "<div class=\"flex-badge-container\" data-toggle=\"tooltip\" title=\"Forks\">" +
        "<i class=\"octicon octicon-repo-forked\" aria-hidden=\"true\"></i>" +
        "<div class=\"repo-statum\">" +
        count +
        "</div></div>";
    }
    return new Handlebars.SafeString(out);
});

// Helper for latest release
Handlebars.registerHelper("releaseinfo", function(release) {
    var out = "";
    if (null != release) {
        out = out +
        "<div class=\"flex-datum-container\">" +
        "<small><small>latest release:<br />" +
        "<a target=\"_blank\" href=\"" +
        release.url + 
        "\">" +
        release.name +
        "</a></small></small></div>";
    }
    return new Handlebars.SafeString(out);
});

// Helper for latest update
Handlebars.registerHelper("updateinfo", function(days) {
    var out = "";
    if (null != days) {
        out = out +
        "<div class=\"flex-datum-container\">" +
        "<small><small>latest update:<br />" +
        days + 
        " days ago</small></small></div>";
    }
    return new Handlebars.SafeString(out);
});

// Helper for links
Handlebars.registerHelper("link", function(link) {
    var out = "<a target=\"_blank\" href=\"" + link.url + "\">";
    if (link.type == "github") {
        out = out + 
        "<i class=\"fa fa-github\" aria-hidden=\"true\"></i> " +
        Handlebars.escapeExpression(link.id) +
        "</a>";
    } else if (link.type == "twitter") {
        out = out + 
        "<i class=\"fa fa-twitter\" aria-hidden=\"true\"></i> @" +
        Handlebars.escapeExpression(link.id) +
        "</a>";
    } else if (link.type == "homepage") {
        out = out + 
        "<i class=\"fa fa-home\" aria-hidden=\"true\"></i> " +
        Handlebars.escapeExpression(link.id) +
        "</a>";
    } else {
        out = out + 
        Handlebars.escapeExpression(link.url) +
        "</a>";
    }
    return new Handlebars.SafeString(out);
});

/* Data
* ----
*/
// gets the modules
function getModulesListing(query) {
    if (query) {
        query = '/search?q=' + encodeURIComponent(query);
    } else {
        query = '/modules';
    }
    $.getJSON(query)
    .done(function ( data ) {
        // update the search's meta data
        $( "#results-meta" )
        .empty()
        .append(
            "<p>" +
            data.results + " module" + (1 == data.results ? "" : "s") +
            " (<span data-toggle=\"tooltip\" title=\"" +
            "Search: " + data.search_duration + "ms, "  +
            "fetch: " + data.fetch_duration + "ms" +
            "\">" + data.total_duration + "ms</span>)"
        );
        
        // render the results
        var source   = $("#modules-template").html();
        var template = Handlebars.compile(source);
        var html = template(data);
        $( "#modules-list" )
        .empty()
        .append(html);
        
        // opt-in for tooltips
        $('[data-toggle="tooltip"]').tooltip();
    });
}

/* UI helpers
* ----------
*/
// Sets the layout for the page
function setDisplayLayout(layout) {
    // turn off currently selected layout
    $( "#btngrpLayout .btn" ).removeClass("btn-primary");
    
    // persist layout
    Cookies.set('layout', layout);
    
    switch (layout) {
        case 'list':
        $( "#btnLayoutList" ).addClass("btn-primary");
        break;
        case 'grid':
        $( "#btnLayoutGrid" ).addClass("btn-primary");
        break;
    }
    
    // TODO: actually switch layouts
}

// Switches sort order (triggers a data fetch)
function setDisplaySort(sort) {
    // turn off currently selected sort
    $( ".btnoptSort" ).removeClass("active");
    
    // persist sort
    Cookies.set('sort', sort);
    
    // make current sort appear active
    var optclass = "#btnopt" + sort.charAt(0).toUpperCase() + sort.slice(1);
    $( optclass ).addClass('active');
    
    // set value and text of sort button to selected option
    $( "#btnSort" ).val(sort);
    $( "#btnSort" ).text( $( optclass ).text() ).append( $( '<span class="caret caret-right" aria-hidden="true"></span>' ) );
    
    // refresh listings
    getModulesListing();
}

/* Forms
* -----
*/

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function submitModuleError(xhr, status, err) {
    $( "#submitProgress" ).hide();
    $( "#submitResult" )
        .empty()
        .append('<div class="alert alert-danger" role="alert">Borked: ' + err + '</div>');
}

function submitModulePoll(data) {
    console.log(data)
    if ('queued' == data.status || 'started' == data.status) {
        return setTimeout(function() {
            $.ajax({
                type: "GET",
                url: "submit",
                data: { 'jobid': data.jobid },
                success: submitModulePoll,
                error: submitModuleError
            })
         }, 1000);
    }
    if ('failed' == data.status) {
        submitModuleError(null, null, data.message);
    }
    if ('finished' == data.status) {
        $( "#submitProgress" ).hide();
        $( "#modalSubmit" ).modal('hide');
        $( "#modalSubmitDone .modal-body")
            .empty()
            .append(
                '<a target="_blank" href="' +
                data.url + '">Track pull request #' +
                data.pull + '</a>');
        $( "#modalSubmitDone" ).modal('show');
    }
}

function submitModule(e) {
    e.stopPropagation();
    if (e.isDefaultPrevented()) {
        console.log('Invalid form input?!?');
        return;
    } else {
        e.preventDefault();
        $( "#submitProgress" ).show();
        $.ajax({
            type: "POST",
            url: "submit",
            data: $(this).serialize(),
            success: submitModulePoll,
            error: submitModuleError
        });
    }
}

/* Settings
* --------
*/
// Get a cookie's value, or set it to a default one
function CookieGet(name, defaultval) {
    var s = Cookies.get(name);
    if (s == undefined) {
      s = defaultval;
      Cookies.set(name, s);
    }
    return s;
}