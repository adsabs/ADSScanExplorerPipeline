from elasticsearch import Elasticsearch
import json
import argparse
from adsputils import setup_logging, load_config
from distutils.util import strtobool
import os

# ============================= INITIALIZATION ==================================== #

proj_home = os.path.realpath(os.path.dirname(__file__))
config = load_config(proj_home=proj_home)
logger = setup_logging('setup_db.py', proj_home=proj_home,
                        level=config.get('LOGGING_LEVEL', 'INFO'),
                        attach_stdout=config.get('LOG_STDOUT', False))

# =============================== FUNCTIONS ======================================= #

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--re-create",
                    dest="delete",
                    required=False,
                    default="False",
                    type=str,
                    help="Deletes existing ads_scan_explorer index before creating a new fresh instance")
    args = parser.parse_args()


es = Elasticsearch(config.get("ELASTIC_SEARCH_URL", ""))
if bool(strtobool(args.delete)):
    es.indices.delete(index = config.get("ELASTIC_SEARCH_INDEX", ""))

es_mapping_file = "./es/ocr.json"

with open(es_mapping_file, 'r') as f:
    index_dict = json.load(f)
    es.indices.create(index = config.get("ELASTIC_SEARCH_INDEX", ""), mappings = index_dict)
es.transport.close()