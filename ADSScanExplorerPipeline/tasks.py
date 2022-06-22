from concurrent.futures import process
import requests
import os
import uuid
from ADSScanExplorerPipeline.models import JournalVolume, VolumeStatus
from ADSScanExplorerPipeline.ingestor import parse_top_file, parse_dat_file, parse_image_files, identify_journals, upload_image_files
from ADSScanExplorerPipeline.ingestor import check_all_image_files_exists, index_ocr_files, set_ingestion_error_status, set_correct_volume_status
from kombu import Queue
import ADSScanExplorerPipeline.app as app_module
from adsputils import load_config



# ============================= INITIALIZATION ==================================== #

proj_home = os.path.realpath(os.path.join(os.path.dirname(__file__), '../'))
config = load_config(proj_home=proj_home)
app = app_module.ADSScanExplorerPipeline('ads-scan-pipeline', proj_home=proj_home, local_config=globals().get('local_config', {}))
logger = app.logger

app.conf.CELERY_QUEUES = (
    Queue('process-volume', app.exchange, routing_key='process-volume'),
    Queue('process-new-volumes', app.exchange, routing_key='investigate-new-volumes'),
)

# ============================= TASKS ============================================= #

@app.task(queue='process-volume')
def task_process_volume(base_path: str, journal_volume_id: str, upload_files: bool = False, index_ocr: bool = False, upload_db: bool = True):
    """
    Processes a journal volume
    """
    logger.info("Processing journal_volume id: %s", journal_volume_id)
    error_msg = ""  
    with app.session_scope() as session:
        vol = None
        try:
            vol = JournalVolume.get_from_id_or_name(journal_volume_id, session)
            vol.status = VolumeStatus.Processing
            session.add(vol)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to get journal_volume: %s from db: %s", journal_volume_id, e)
            return
        try:
            top_filename = vol.journal + vol.volume + ".top"
            top_file_path = os.path.join(base_path, config.get('TOP_SUB_DIR', ''), vol.type, vol.journal, top_filename)
            dat_file_path = top_file_path.replace(".top", ".dat")
            image_path = os.path.join(base_path, config.get('BITMAP_SUB_DIR', ''), vol.type, vol.journal, vol.volume, "600")

            for page in parse_top_file(top_file_path, vol, session):
                session.add(page)
                vol.pages.append(page)

            for article in parse_dat_file(dat_file_path, vol, session):
                session.add(article)
                vol.articles.append(article)

            check_all_image_files_exists(image_path, vol, session)

            for page in parse_image_files(image_path, vol, session):
                session.add(page)

            vol.db_done = True
            set_correct_volume_status(vol, session)
            
        except Exception as e:
            session.rollback()
            logger.error("Failed to process journal_volume_id: %s due to: %s", str(journal_volume_id), e)
            error_msg = str(e)
    if error_msg != "":
        set_ingestion_error_status(session, journal_volume_id, error_msg)
        return
    
    if upload_files:
        task_upload_image_files_for_volume.delay(base_path, journal_volume_id)
    if index_ocr:
        task_index_ocr_files_for_volume.delay(base_path, journal_volume_id)
    if upload_db:
        task_upload_db_for_volume.delay(journal_volume_id)


    set_correct_volume_status(vol, session)   
    return session

@app.task(queue='process-volume')
def task_upload_db_for_volume(journal_volume_id: str):
    """
    Uploads the DB metadata to the service DB through a API call to the service
    """
    logger.info("Uploading db for journal_volume id: %s", journal_volume_id)
    error_msg = ""  
    with app.session_scope() as session:
        vol = None
        try:
            vol = JournalVolume.get_from_id_or_name(journal_volume_id, session)
            url = config.get('SERVICE_DB_PUSH_URL' ,'')
            x = requests.put(url, json = vol.to_dict())
            logger.info(x)
            if x.status_code == 200:
                vol.db_uploaded = True
                set_correct_volume_status(vol, session)
            else:
                raise Exception(x.content)
        except Exception as e:
            session.rollback()
            logger.error("Failed to upload db from journal_volume_id: %s due to: %s", str(journal_volume_id), e)
            error_msg = str(e)
    if error_msg != "":
        set_ingestion_error_status(session, journal_volume_id, error_msg)
    return session

@app.task(queue='process-volume')
def task_upload_image_files_for_volume(base_path: str, journal_volume_id: str):
    error_msg = ""
    logger.info("Uploading images files for volume %s", journal_volume_id)
    with app.session_scope() as session:
        vol = None
        try:
            vol = JournalVolume.get_from_id_or_name(journal_volume_id, session)
            image_path = os.path.join(base_path, config.get('BITMAP_SUB_DIR', ''), vol.type, vol.journal, vol.volume, "600")
            check_all_image_files_exists(image_path, vol, session)
            upload_image_files(image_path, vol, session)
            vol.bucket_uploaded = True
            vol.status_message = None
            session.add(vol)
        except Exception as e:
            session.rollback()
            logger.error("Failed to upload images from journal_volume_id: %s due to: %s", str(journal_volume_id), e)
            error_msg = str(e)
    if error_msg != "":
        set_ingestion_error_status(session, journal_volume_id, error_msg)
    return session

@app.task(queue='process-volume')
def task_index_ocr_files_for_volume(base_path: str, journal_volume_id: str):
    error_msg = ""
    logger.info("Indexing ocr files for volume %s", journal_volume_id)

    with app.session_scope() as session:
        vol = None
        try:
            vol = JournalVolume.get_from_id_or_name(journal_volume_id, session)
            ocr_path = os.path.join(base_path, config.get('OCR_SUB_DIR', ''), vol.type, vol.journal, vol.volume)
            index_ocr_files(ocr_path, vol, session)
            vol.ocr_uploaded = True
            set_correct_volume_status(vol, session)
        except Exception as e:
            session.rollback()
            logger.warn("Failed to index ocr files from journal_volume_id: %s due to: %s", str(journal_volume_id), e)
            error_msg = str(e)
    if error_msg != "":
        set_ingestion_error_status(session, journal_volume_id, error_msg)
    return session

@app.task(queue='process-new-volumes')
def task_process_new_volumes(base_path: str, upload_files: bool = False, index_ocr: bool = False,  upload_db: bool = True, process: bool = True, dry_run: bool = False):
    """
    Investigate if any new or updated volumes exists and process them if process flag is set to True
    """
    logger.info("Investigating new or changed volumes in %s", base_path)
    volumes_to_process = []
    with app.session_scope() as session:
        for vol in identify_journals(base_path):
            existing_vol = JournalVolume.get_from_obj(vol, session)
            if existing_vol:
                if vol.file_hash != existing_vol.file_hash:
                        existing_vol.status = VolumeStatus.Update
                        existing_vol.file_hash = vol.file_hash
                        if dry_run:
                            logger.info("DRY RUN: Volume: %s would have been updated", str(vol.id))
                        else:
                            session.add(existing_vol)
            else:
                if vol.status != VolumeStatus.Error:
                    vol.status = VolumeStatus.New
                if dry_run:
                    logger.info("DRY RUN: Volume: %s would have been added", str(vol.id))
                else:
                    session.add(vol)
                
        for vol in JournalVolume.get_to_be_processed(session):
            volumes_to_process.append(vol.id)
    if process and not dry_run:
        for vol_id in volumes_to_process:
            task_process_volume.delay(base_path, vol_id, upload_files, index_ocr, upload_db, dry_run)
    return session

if __name__ == '__main__':
    app.start()
