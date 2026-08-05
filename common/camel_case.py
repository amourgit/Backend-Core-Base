"""
common/camel_case.py
=====================

Le frontend (schémas Zod dans src/types/models/*.ts) attend des clés JSON
en camelCase (`nomAffiche`, `createdAt`, `estEpingle`...), alors que Django
REST Framework et les modèles Python utilisent naturellement le snake_case.

Plutôt que d'imposer au frontend de connaître la casse Python, ou de
dupliquer manuellement chaque champ de chaque serializer avec un
`source=`, on convertit la frontière JSON une bonne fois pour toutes ici :
tout ce qui sort de l'API est automatiquement re-casé en camelCase, et
tout ce qui entre (body JSON) est re-casé en snake_case avant de toucher
les serializers. Le code Python (models, serializers, vues) reste 100%
snake_case, idiomatique Django, du début à la fin.

Volontairement auto-suffisant (pas de dépendance externe type
djangorestframework-camel-case) pour rester simple à auditer.
"""

import re

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer

_UNDERSCORE_RE = re.compile(r'_([a-zA-Z0-9])')
_CAMEL_RE = re.compile(r'(?<!^)(?=[A-Z])')


def to_camel_case(snake_str: str) -> str:
    """`nom_affiche` -> `nomAffiche`. Préserve les underscores de tête (`_private`)."""
    if not isinstance(snake_str, str) or not snake_str:
        return snake_str
    return _UNDERSCORE_RE.sub(lambda m: m.group(1).upper(), snake_str)


def to_snake_case(camel_str: str) -> str:
    """`nomAffiche` -> `nom_affiche`."""
    if not isinstance(camel_str, str) or not camel_str:
        return camel_str
    return _CAMEL_RE.sub('_', camel_str).lower()


def _convert_keys(data, converter):
    if isinstance(data, dict):
        return {converter(key): _convert_keys(value, converter) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_convert_keys(item, converter) for item in data]
    return data


class CamelCaseJSONRenderer(JSONRenderer):
    """Convertit récursivement toutes les clés de la réponse en camelCase."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        camel_data = _convert_keys(data, to_camel_case)
        return super().render(camel_data, accepted_media_type, renderer_context)


class CamelCaseJSONParser(JSONParser):
    """Convertit récursivement toutes les clés du corps de requête en snake_case
    avant que DRF ne les transmette au serializer."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        return _convert_keys(data, to_snake_case)
