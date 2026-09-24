"""Validator for the exact JSON Schema keywords used by this teaching pack.
Not a general JSON Schema or FHIR validator. Unknown keywords fail explicitly.
"""
import re,math
from datetime import date
SUPPORTED={'$schema','title','type','properties','required','additionalProperties','items','minItems','uniqueItems','enum','const','minimum','maximum','minLength','pattern','format'}
def validate(value,schema,path='$'):
    unknown=set(schema)-SUPPORTED
    if unknown:raise ValueError(f'Unsupported schema keywords: {unknown}')
    if 'const' in schema and value!=schema['const']:raise ValueError(path+' const')
    if 'enum' in schema and value not in schema['enum']:raise ValueError(path+' enum')
    types=schema.get('type');types=[types] if isinstance(types,str) else types
    checks={'null':lambda v:v is None,'string':lambda v:isinstance(v,str),'number':lambda v:isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v),'integer':lambda v:isinstance(v,int) and not isinstance(v,bool),'boolean':lambda v:isinstance(v,bool),'object':lambda v:isinstance(v,dict),'array':lambda v:isinstance(v,list)}
    if types and not any(checks[t](value) for t in types):raise ValueError(path+' type')
    if isinstance(value,dict):
        if not set(schema.get('required',[]))<=set(value):raise ValueError(path+' required')
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and not set(value)<=set(props):raise ValueError(path+' additionalProperties')
        for k,v in value.items():
            if k in props:validate(v,props[k],path+'/'+k)
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0):raise ValueError(path+' minItems')
        if schema.get('uniqueItems') and any(v in value[:i] for i,v in enumerate(value)):raise ValueError(path+' uniqueItems')
        if 'items' in schema:
            for i,v in enumerate(value):validate(v,schema['items'],path+'/'+str(i))
    if isinstance(value,str):
        if len(value)<schema.get('minLength',0):raise ValueError(path+' minLength')
        if 'pattern' in schema and not re.search(schema['pattern'],value):raise ValueError(path+' pattern')
        if schema.get('format')=='date':
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError(path+' date format')
            date.fromisoformat(value)
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if 'minimum' in schema and value<schema['minimum']:raise ValueError(path+' minimum')
        if 'maximum' in schema and value>schema['maximum']:raise ValueError(path+' maximum')
