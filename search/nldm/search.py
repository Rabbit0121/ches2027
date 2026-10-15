"""NLDM search: retain physical alternatives and time the assembled source DAG."""
from ...timing.library import read_library
from ..common.bidirectional import Search
from ..common.oracle import Oracle
from ..common.settings import configured_path, search_config
from .timing import NLDM


def make_timing(profile, settings):
    library = read_library(configured_path(profile['liberty']))
    return NLDM(library, settings['slew_ps']), library, None


def create_search(problem, profile, settings, seconds=None):
    measure, library, _ = make_timing(profile, settings)
    config = search_config(settings, 'nldm', seconds)
    factory = lambda s: Oracle(s, measure, library, load_ff=settings['load_ff'])
    return Search(problem, factory, config)
