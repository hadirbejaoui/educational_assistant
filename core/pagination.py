from django.core.paginator import Paginator

DEFAULT_PER_PAGE = 12


def paginate(request, queryset, per_page=DEFAULT_PER_PAGE):
    """Retourne la page demandée (?page=N) d'une liste.

    `get_page` ne lève jamais d'erreur : une page invalide ou hors limites
    renvoie la première ou la dernière page.
    """
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))
