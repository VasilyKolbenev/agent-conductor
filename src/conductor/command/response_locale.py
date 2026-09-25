"""Localize derived presentation only; immutable documents and rules stay exact."""
from collections.abc import Mapping


def language_for(headers):
    choices=[]
    for name,value in headers:
        if name.lower() != "accept-language":
            continue
        for position,part in enumerate(value[:512].split(',')):
            fields=part.strip().lower().split(';')
            language=fields[0].split('-')[0]
            quality=1.0
            try:
                for field in fields[1:]:
                    if field.strip().startswith('q='):
                        quality=float(field.strip()[2:])
            except ValueError:
                continue
            if language in {'en','ru'} and 0 < quality <= 1:
                choices.append((quality,-position,language))
    return max(choices)[2] if choices else 'en'


def localize_criteria(payload, locale):
    if locale != 'ru':
        return payload
    result=dict(payload)
    graph=payload.get('graph')
    if isinstance(graph,Mapping) and 'success_criteria' in graph and graph.get('definition'):
        from .graph_definition import GraphDefinition
        from .success_criteria import for_plan
        definition=GraphDefinition.from_dict(graph['definition'])
        result['graph']={**graph,'success_criteria':for_plan(definition.nodes,locale=locale)}
    if 'success_criteria' in payload and 'published' in payload and 'draft' in payload:
        from .graph_template import TemplateNode
        from .success_criteria import for_document
        draft=payload.get('draft')
        document=draft.get('document') if isinstance(draft,Mapping) else payload.get('published')
        if isinstance(document,Mapping):
            nodes=tuple(TemplateNode.from_dict(row) for row in document.get('nodes',()))
            result['success_criteria']=for_document(nodes,locale=locale)
    return result
