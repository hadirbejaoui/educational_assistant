"""Balises de gabarit de l'interface.

- {% asset "css/tokens.css" %} : URL d'un fichier statique suivie de ?v=<date de
  modification>. Dès qu'un fichier change, son URL change : le navigateur ne peut
  plus réutiliser une ancienne version en cache (cache-busting).
- {% page_header title="…" subtitle="…" back_url=… back_label="…" %}actions{% endpage_header %} :
  en-tête de page standard (titre, sous-titre, lien retour, actions à droite).
"""

import os
import re

from django import template
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils.html import escape
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


_MD_HEADING = re.compile(r"^(#{1,6})\s+(?:#+\s+)*(.*)$")  # « ### ### Titre » toléré
_MD_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _inline(text):
    """Échappe le texte puis rend le gras **…** (seule mise en forme en ligne acceptée)."""
    return _MD_BOLD.sub(r"<strong>\1</strong>", escape(text.strip()))


@register.filter
def rich_text(text):
    """Texte généré (résumé) -> HTML sûr : intertitres « ## », listes « - », gras, paragraphes.

    Tout le texte est échappé : seules les balises produites ici sont du HTML.
    Les anciens résumés en texte simple s'affichent comme avec |linebreaks.
    """
    html, paragraph, items = [], [], []

    def flush():
        if paragraph:
            html.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()
        if items:
            html.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
            items.clear()

    for line in str(text or "").splitlines():
        heading, bullet = _MD_HEADING.match(line.strip()), _MD_BULLET.match(line)
        if not line.strip():
            flush()
        elif heading:
            flush()
            level = 3 if len(heading.group(1)) <= 2 else 4  # h1/h2 sont déjà ceux de la page
            html.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif bullet:
            if paragraph:
                flush()
            items.append(bullet.group(1))
        else:
            if items:
                flush()
            paragraph.append(line)
    flush()
    return mark_safe("\n".join(html))
