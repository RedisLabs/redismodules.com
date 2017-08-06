// Helper for stargazers badge
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

function getModulesListing() {
    $.getJSON('/modules')
        .done(function ( data ) {
            var source   = $("#module-template").html();
            var template = Handlebars.compile(source);
            var html = template(data);
            $( "#modules-list" ).append(html);

            // opt-in for tooltips
            $('[data-toggle="tooltip"]').tooltip();
        });
}