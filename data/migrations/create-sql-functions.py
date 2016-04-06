from collections import namedtuple
from jinja2 import Environment
from jinja2 import FileSystemLoader
from TileStache.Goodies.VecTiles.transform import _parse_kt
import os.path
import yaml

# Rule = namedtuple(
#     'Rule',
#     'calc equals not_equals not_exists set_memberships exists default_rule'
# )


class EqualsRule(object):

    def __init__(self, column, value):
        self.column = column
        self.value = value

    def as_sql(self):
        return '%s = %s' % (self.column, self.value)

    def columns(self):
        return [self.column]


class SetRule(object):

    def __init__(self, column, values):
        self.column = column
        self.values = values

    def as_sql(self):
        return '%s IN ()' % (self.column, ', '.join(self.values))

    def columns(self):
        return [self.column]


class AndRule(object):

    def __init__(self, rules):
        self.rules = rules

    def as_sql(self):
        return ' AND '.join([x.as_sql() for x in self.rules])

    def columns(self):
        return sum([x.columns() for x in self.rules])


class OrRule(object):

    def __init__(self, rules):
        self.rules = rules

    def as_sql(self):
        return ' OR '.join([x.as_sql() for x in self.rules])

    def columns(self):
        return sum([x.columns() for x in self.rules])


class NotRule(object):

    def __init__(self, rule):
        self.rule = rule

    def as_sql(self):
        return 'NOT (%s)' % self.rule.as_sql()

    def columns(self):
        return self.rule.columns()


def format_string_value(value):
    formatted_value = "'%s'" % value
    return formatted_value


def format_calc_value(value):
    if value.startswith('${') and value.endswith('}'):
        calc_value = value[2:-1]
    else:
        # calc_value = format_string_value(value)
        calc_value = value
    return calc_value


def create_filter_rule(filter_key, filter_value):
    # check for the composite rules first
    if filter_key == 'not':
        return NotRule(create_filter_rule(filter_value))
    elif filter_key == 'all':
        rules = []
        for k, v in filter_value.items():
            rule = create_filter_rule(k, v)
            rules.append(rule)
        assert rules, 'all rule specified with no sub rules'
        if len(rules) > 1:
            rule = AndRule(rules)
        else:
            rule = rules[0]
        return rule
    elif filter_key == 'any':
        rules = []
        for k, v in filter_value.items():
            rule = create_filter_rule(k, v)
            rules.append(rule)
        assert rules, 'all rule specified with no sub rules'
        if len(rules) > 1:
            rule = OrRule(rules)
        else:
            rule = rules[0]
        return rule
    else:
        # leaf rules
        if isinstance(filter_value, list):
            return SetRule(filter_key, filter_value)
        else:
            return EqualsRule(filter_key, filter_value)


class Matcher(object):

    def __init__(self, rule, min_zoom, output, table):
        self.rule = rule
        self.min_zoom = min_zoom
        self.output = output
        self.table = table

    def when_sql_output(self):
        hstore_output = ','.join(
            ['%s=>%s' % (k, v) for k, v in self.output.items()])
        return 'WHEN %s THEN HSTORE(%s)' % (self.rule.as_sql(), hstore_output)

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
        when_parts.append(when_sql_part)
    when_sql = '\n'.join(when_parts)
    case_sql = 'CASE\n%s\nEND' % when_sql
    return case_sql


layers = {}
script_root = os.path.dirname(__file__)

for layer in ('landuse', 'pois', 'transit', 'water'):
    kind_rules = []
    min_zoom_rules = []
    file_path = os.path.join(script_root, layer)
    with open(file_path) as fh:
        yaml_data = yaml.load(fh)
        matchers = []
        for yaml_datum in yaml_data:
            matcher = create_matcher(yaml_datum)
            matcher.append(matcher)

    # TODO handle params!
    # need to iterate through the matchers
    # because the columns are grouped by the table on a per matcher basis anyway
    params = set(sum([x.columns() for x in matchers]))
    osm_tags = set([Key(table='osm', key='tags', typ='hstore'),
                    Key(table=None, key='tags', typ='hstore')])
    params = ((used_params(kind_rules) | used_params(min_zoom_rules))
              - osm_tags)
    # sorted params is nicer to read in the sql
    params = sorted(params)
    kind_case_statement = create_case_statement_kind(matchers)
    min_zoom_case_statement = create_case_statement_min_zoom(matchers)
    layers[layer] = dict(
        params=params,
        kind_case_statement=kind_case_statement,
        min_zoom_case_statement=min_zoom_case_statement,
    )

import sys
sys.exit(0)

template_name = os.path.join(script_root, 'sql.jinja2')
environment = Environment(loader=FileSystemLoader('.'))
template = environment.get_template(template_name)
sql = template.render(
    layers=layers,
)
print sql
