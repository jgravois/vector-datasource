from collections import namedtuple
from jinja2 import Environment
from jinja2 import FileSystemLoader
from TileStache.Goodies.VecTiles.transform import _parse_kt
import os.path
import yaml


def format_string_value(s):
    return "'%s'" % s


def format_key(k):
    if k.startswith('tags->'):
        val = "tags->'%s'" % (k[len('tags->'):])
    else:
        val = format_string_value(k)
    return val


class EqualsRule(object):

    def __init__(self, column, value):
        self.column = column
        self.value = value

    def as_sql(self):
        return '%s = %s' % (
            format_key(self.column),
            format_string_value(self.value))

    def columns(self):
        return [self.column]


class SetRule(object):

    def __init__(self, column, values):
        self.column = column
        self.values = values

    def as_sql(self):
        formatted_values = map(format_string_value, self.values)
        return '%s IN (%s)' % (
            format_key(self.column),
            ', '.join(formatted_values))

    def columns(self):
        return [self.column]


class AndRule(object):

    def __init__(self, rules):
        self.rules = rules

    def as_sql(self):
        return ' AND '.join([x.as_sql() for x in self.rules])

    def columns(self):
        return sum([x.columns() for x in self.rules], [])


class OrRule(object):

    def __init__(self, rules):
        self.rules = rules

    def as_sql(self):
        return ' OR '.join([x.as_sql() for x in self.rules])

    def columns(self):
        return sum([x.columns() for x in self.rules], [])


class NotRule(object):

    def __init__(self, rule):
        self.rule = rule

    def as_sql(self):
        return 'NOT (%s)' % self.rule.as_sql()

    def columns(self):
        return self.rule.columns()


def create_level_filter_rule(filter_level, combinator=AndRule):
    rules = []
    for k, v in filter_level.items():
        rule = create_filter_rule(k, v)
        rules.append(rule)
    assert rules, 'No rules specified in level: %s' % filter_level
    if len(rules) > 1:
        rule = combinator(rules)
    else:
        rule = rules[0]
    return rule


def create_filter_rule(filter_key, filter_value):
    # check for the composite rules first
    if filter_key == 'not':
        rule = create_level_filter_rule(filter_value)
        rule = NotRule(rule)
    elif filter_key == 'all':
        rule = create_level_filter_rule(filter_value)
    elif filter_key == 'any':
        rule = create_level_filter_rule(filter_value, combinator=OrRule)
    else:
        # leaf rules
        if isinstance(filter_value, list):
            rule = SetRule(filter_key, filter_value)
        else:
            rule = EqualsRule(filter_key, filter_value)
    return rule


class Matcher(object):

    def __init__(self, rule, min_zoom, output, table):
        self.rule = rule
        self.min_zoom = min_zoom
        self.output = output
        self.table = table

    def when_sql_output(self):
        hstore_output = ','.join(
            ['%s=>%s' % (k, v) for k, v in self.output.items()])
        return "WHEN %s THEN HSTORE('%s')" % (
            self.rule.as_sql(), hstore_output)

    def when_sql_min_zoom(self):
        return 'WHEN %s THEN %s' % (self.rule.as_sql(), self.min_zoom)


def create_matcher(yaml_datum):
    rules = []
    for k, v in yaml_datum['filter'].items():
        rule = create_filter_rule(k, v)
        rules.append(rule)
    assert rules, 'No filter rules found in %s' % yaml_datum
    if len(rules) > 1:
        rule = AndRule(rules)
    else:
        rule = rules[0]
    min_zoom = yaml_datum['min_zoom']
    output = yaml_datum['output']
    table = yaml_datum.get('table')
    matcher = Matcher(rule, min_zoom, output, table)
    return matcher


def create_case_statement_min_zoom(matchers):
    when_parts = []
    for matcher in matchers:
        when_sql_part = matcher.when_sql_min_zoom()
        # indent
        when_sql_part = '    %s' % when_sql_part
        when_parts.append(when_sql_part)
    when_sql = '\n'.join(when_parts)
    case_sql = 'CASE\n%s\n  END' % when_sql
    return case_sql


def create_case_statement_output(matchers):
    when_parts = []
    for matcher in matchers:
        when_sql_part = matcher.when_sql_output()
        # indent
        when_sql_part = '    %s' % when_sql_part
        when_parts.append(when_sql_part)
    when_sql = '\n'.join(when_parts)
    case_sql = 'CASE\n%s\n  END' % when_sql
    return case_sql

Key = namedtuple('Key', 'table key typ')


layers = {}
script_root = os.path.dirname(__file__)

for layer in ('landuse', 'pois', 'transit', 'water'):
    kind_rules = []
    min_zoom_rules = []
    file_path = os.path.join(script_root, '%s.yaml' % layer)
    with open(file_path) as fh:
        yaml_data = yaml.load(fh)
        matchers = []
        for yaml_datum in yaml_data:
            matcher = create_matcher(yaml_datum)
            matchers.append(matcher)

    params = set()
    for matcher in matchers:
        columns = matcher.rule.columns()
        for column in columns:
            if not column.startswith('tags'):
                key = Key(table=matcher.table, key=column, typ='text')
                params.add(key)

    # osm_tags = set([Key(table='osm', key='tags', typ='hstore'),
    #                 Key(table=None, key='tags', typ='hstore')])
    # params = ((used_params(kind_rules) | used_params(min_zoom_rules))
    #           - osm_tags)

    # sorted params is nicer to read in the sql
    params = sorted(params)

    min_zoom_case_statement = create_case_statement_min_zoom(matchers)
    kind_case_statement = create_case_statement_output(matchers)
    layers[layer] = dict(
        params=params,
        kind_case_statement=kind_case_statement,
        min_zoom_case_statement=min_zoom_case_statement,
    )

template_name = os.path.join(script_root, 'sql.jinja2')
environment = Environment(loader=FileSystemLoader('.'))
template = environment.get_template(template_name)
sql = template.render(
    layers=layers,
)
print sql
