"""Practice search: characterized-path ranking and complete mapped-STA acceptance."""
from ...timing.library import read_library
from ..common.bidirectional import Search
from ..common.oracle import Oracle
from ..common.settings import configured_path, search_config
from .sta import MappedSTA
from .path_score import PathTable


def make_timing(profile, settings):
    path = configured_path(profile['liberty'])
    library = read_library(path)
    if any('the/path/of/' in token for token in settings['eda_command']):
        raise ValueError('Configure the external EDA adapter command')
    measure = MappedSTA(settings['eda_command'], path, settings['slew_ps'])
    paths = PathTable(measure, settings['path_depth'], settings['path_budget'], settings['load_ff'])
    return measure, library, paths


def create_search(problem, profile, settings, seconds=None):
    measure, library, paths = make_timing(profile, settings)
    config = search_config(settings, 'measured', seconds)
    factory = lambda s: Oracle(s, measure, library, paths, settings['load_ff'])
    return Search(problem, factory, config)
