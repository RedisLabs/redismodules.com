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
    $( "#btnSort" )
        .text( $( optclass ).text() )
        .append( $( '<span class="caret caret-right" aria-hidden="true"></span>' ) );
    
    // refresh listings
    getModulesListing();
}

/* Forms
* -----
*/

// Updates submit module alert
// W/o arguments cleans everything
function submitModuleError(xhr, status, err) {
    // TODO: betterize
    if (err) {
        $( "#submitProgress" ).hide();
        $( "#formSubmitModule :submit" ).removeClass('disabled');
        $( "#submitResult .alert" )
            .remove();
        $( "#submitResult" )
            .append('<div class="alert alert-danger submit-alert" role="alert">' + err + '</div>');
    } else {
        $( "#submitResult .alert" )
        .remove();
    }
}

// Updates submit module alert
// W/o arguments cleans everything
function submitModuleSuccess(msg) {
    $( "#submitProgress" ).hide();
    $( "#formSubmitModule :submit" ).removeClass('disabled');
    $( "#submitResult .alert" )
        .remove();
    $( "#submitResult" )
        .append('<div class="alert alert-success submit-alert" role="alert">' + msg + '</div>');
}

function submitModulePoll(data) {
    if ('failed' != data.status && 'finished' != data.status) {
        return setTimeout(function() {
            $( "#submitProgress .progress-bar" )
                .text(data.message + '...');
            $.ajax({
                type: "GET",
                url: "submit",
                data: { 'id': data.id },
                success: submitModulePoll,
                error: submitModuleError
            })
         }, 1000);
    } else if ('failed' == data.status) {
        submitModuleError(null, null, data.message);
    } else if ('finished' == data.status) {
        $( "#submitProgress" ).hide();
        $( "#submitProgress .progress-bar" )
            .text('');
        $( "#formSubmitModule :submit" ).removeClass('disabled');
        $( "#submitResult .alert" )
            .remove();
        submitModuleSuccess(
            'Module submitted - track the submission via ' +
            '<a target="_blank" href="' + data.pull_url + '">' +
                'pull request #' + data.pull_number +
            '</a>');
    }
}

function submitModule(e) {
    e.stopPropagation();
    if (e.isDefaultPrevented()) {
        submitModuleError(null, null, 'Invalid form input');
        return;
    } else {
        e.preventDefault();
        submitModuleError();    // clear residuals
        $( "#formSubmitModule :submit" ).addClass('disabled');
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

/* General
* --------
*/
function init() {
    // Bindings
    // Listen to clicks on the display layout button
    $( "#btngrpLayout .btn" ).click(function(e) {
        e.preventDefault();
        setDisplayLayout($(this).attr('role'));
    });
  
    // Listen to clicks on the sort button
    $( ".btnoptSort" ).click( function(e) {
    e.preventDefault();
    setDisplaySort($(this).attr('role'));
    });
      
    // Handle "Subit module" form submit event
    $( "#formSubmitModule" ).on('submit', submitModule);
  
    // Create modal dialogs
    $( "#intro #modals a" )
    .each(function(index) {
        var lbl = $( this ).text().replace(/\s/g, '');
        var uri = encodeURIComponent($( this ).text().trim());
        $( "#intro #modals" ).after(
            '<div class="modal fade" id="modal' + lbl + '" tabindex="-1" role="dialog" aria-labelledby="modal' + 
             lbl + 'Label" data-remote="moar/' + uri + '">' +
                '<div class="modal-dialog modal-lg" role="document">' +
                    '<div class="modal-content"></div>' +
                '</div>' +
            '</div>'
        );
    });
}