# ADSScanExplorerPipeline
## Logic
The pipeline loops through the input folder structure identifying journal volumes and compare the file status to the ingestion db to detect any updates. The input folder should contain3 subfolders
* bitmaps -- images
* lists -- metadata
* ocr -- ocr files

#TODO Write more of file strucutre
## Setup

* The pipeline needs at at minimum a DB to run the baseline ingestion pipeline. 
* An OpenSearch instance is needed to index the associated OCR files
* A S3 Bucket is needed to upload the actual image files

### Pipeline

Start with setting up the pipeline container. Make sure to set the input folder (with all image files, top files and ocr files) under volumes in the docker-compose.yaml. This will mount the folder into the container making it accessible to run the pipeline. Also make sure to set the S3 Bucket keys in the config.py file.
```
docker compose -f docker/pipeline/docker-compose.yaml up -d
```
This will start a Celery instance. If running on a dev environment you could be running without a RabbitMQ backend with setting CELERY_ALWAYS_EAGER=True in config.py


### Open Search

Setup up the Open Search docker container

```
docker compose -f docker/os/docker-compose.yaml -f docker/os/{environment}.yaml up -d
```

Setup the index by running through the pipeline container:

```
docker exec -it ads_scan_explorer_pipeline python setup_os.py [--re-create] [--update-settings]
```

### Database
Setup a postgresql container
```
docker compose -f docker/postgres/docker-compose.yaml up -d
```

Prepare the database:

```
docker exec -it postgres bash -c "psql -c \"CREATE ROLE scan_explorer WITH LOGIN PASSWORD 'scan_explorer';\""
docker exec -it postgres bash -c "psql -c \"CREATE DATABASE scan_explorer_pipeline;\""
docker exec -it postgres bash -c "psql -c \"GRANT CREATE ON DATABASE scan_explorer_pipeline TO scan_explorer;\""
```

Setup the tables by running through the pipeline container:
```
docker exec -it ads_scan_explorer_pipeline python setup_db.py [--re-create] 
```

## Usage

### Subcommands

| Command | What it does |
|---------|-------------|
| `NEW` | Scans input folder, discovers and processes all new or changed volumes |
| `UPDATE` | Reprocesses all volumes already in the pipeline DB |
| `SINGLE --id <id> [<id2> ...]` | Processes one or more specific volumes by ID (uuid or journal+volume e.g. `ApJ..0333`) |

### Flags (all default to True)

| Flag | What it controls |
|------|-----------------|
| `--process-db=True/False` | Parse metadata files and populate pipeline DB |
| `--upload-db=True/False` | Push volume metadata to the service API |
| `--upload-files=True/False` | Upload TIFF images to S3 |
| `--index-ocr=True/False` | Index OCR text into OpenSearch |
| `--force-update=True/False` | Rerun steps even if already marked complete |

NEW-only flags:

| Flag | What it controls |
|------|-----------------|
| `--process=True/False` | Whether detected volumes should be processed (default True) |
| `--dry-run=True/False` | Detect volumes without writing anything to DB (default False) |

### Examples

Dry-run to see which volumes would be detected:
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles NEW --dry-run=True
```

Discover new volumes without processing them:
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles NEW --process=False
```

Full run (all steps — process DB, push to service, upload images, index OCR):
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles NEW
```

Process DB and push to service, skip S3 upload and OCR indexing:
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles --upload-files=False --index-ocr=False NEW
```

Re-run pipeline DB only (safe — does not touch service DB, S3, or OpenSearch):
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles --upload-db=False --upload-files=False --index-ocr=False --force-update=True UPDATE
```

Push pipeline DB to service DB only (no file re-processing):
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles --process-db=False --upload-db=True --upload-files=False --index-ocr=False --force-update=True UPDATE
```

Re-index OCR into OpenSearch (deletes and re-inserts per volume):
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles --process-db=False --upload-db=False --upload-files=False --index-ocr=True --force-update=True UPDATE
```

Process specific volumes by ID (space-separated):
```
docker exec ads_scan_explorer_pipeline python run.py --input-folder=/proj/ads/articles SINGLE --id ApJ..0333 lls..1969
```