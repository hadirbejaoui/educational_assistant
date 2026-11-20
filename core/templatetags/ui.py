"""Balises de gabarit de l'interface.

- {% asset "css/tokens.css" %} : URL d'un fichier statique suivie de ?v=<date de
  modification>. Dès qu'un fichier change, son URL change : le navigateur ne peut
  plus réutiliser une ancienne version en cache (cache-busting).
- {% page_header title="…" subtitle="…" back_url=… back_label="…" %}actions{% endpage_header %} :
  en-tête de page standard (titre, sous-titre, lien retour, actions à droite).
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def asset(path):
    url = static(path)
    found = finders.find(path)
    if not found:
        return url
    return f"{url}?v={int(os.path.getmtime(found))}"


class PageHeaderNode(template.Node):
    def __init__(self, arguments, nodelist):
        self.arguments = arguments
        self.nodelist = nodelist

    def render(self, context):
        values = {name: value.resolve(context) for name, value in self.arguments.items()}
        # Le contenu vient d'un gabarit déjà rendu (donc déjà échappé) : on le garde tel quel.
        # .strip() renverrait une chaîne « non sûre » qui serait échappée une seconde fois.
        values["actions"] = mark_safe(self.nodelist.render(context).strip())
        return render_to_string("includes/page_header.html", values)


@register.tag("page_header")
def page_header(parser, token):
    arguments = {}
    for bit in token.split_contents()[1:]:
        name, sep, value = bit.partition("=")
        if not sep:
            raise template.TemplateSyntaxError("page_header attend des arguments nom=valeur.")
        arguments[name] = parser.compile_filter(value)
    nodelist = parser.parse(("endpage_header",))
    parser.delete_first_token()
    return PageHeaderNode(arguments, nodelist)


@register.filter
def initials(user):
    """« Hadir Bejaoui » -> « HB » ; à défaut, première lettre du nom d'utilisateur."""
    letters = (user.first_name[:1] + user.last_name[:1]) or user.username[:1]
    return letters.upper()
