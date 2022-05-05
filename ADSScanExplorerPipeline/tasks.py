
import os
import uuid
from ADSScanExplorerPipeline.models import JournalVolume, VolumeStatus
from ADSScanExplorerPipeline.ingestor import parse_top_file, parse_dat_file, parse_image_files, identify_journals
from kombu import Queue
import ADSScanExplorerPipeline.app as app_module
# import adsmsg

# ============================= INITIALIZATION ==================================== #

proj_home = os.path.realpath(os.path.join(os.path.dirname(__file__), '../'))
app = app_module.ADSScanExplorerPipeline('ads-scan-pipeline', proj_home=proj_home, local_config=globals().get('local_config', {}))
logger = app.logger

app.conf.CELERY_QUEUES = (
    Queue('process-volume', app.exchange, routing_key='process-volume'),
    Queue('investigate-new-volumes', app.exchange, routing_key='investigate-new-volumes'),
)

# ============================= TASKS ============================================= #

@app.task(queue='process-volume')
def task_process_volume(journal_volume_id: uuid):
    """
    Processes a journal volume
    """
    with app.session_scope() as session:
        try:
            vol = JournalVolume.get(journal_volume_id, session)
            vol.status = VolumeStatus.Processing
            session.add(vol)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(e)

        try:
            vol = JournalVolume.get(journal_volume_id, session)
            top_filename = vol.journal + vol.volume + ".top"
            base_path = "../ADS_scans_sample"
            top_file_path = os.path.join(base_path, "lists", vol.type, vol.journal, top_filename)
            dat_file_path = top_file_path.replace(".top", ".dat")
            image_path = os.path.join(base_path, "bitmaps", vol.type, vol.journal, vol.volume, "600")
            for page in parse_top_file(top_file_path, vol, session):
                session.add(page)

            for article in parse_dat_file(dat_file_path, vol, session):
                session.add(article)

            for page in parse_image_files(image_path, vol, session):
                session.add(page)
            
            #TODO copy image files
            vol.status = VolumeStatus.Done
        except:
            session.rollback()
            try:
                journal_volume = JournalVolume.get(journal_volume_id, session)
                journal_volume.status = VolumeStatus.Error
                session.add(journal_volume)
                session.commit()
            except Exception as e:
                print(e)
        else:
            session.commit()

@app.task(queue='investigate-new-volumes')
def task_investigate_new_volumes():
    """
    Investigate if any new or updated volumes exists
    """
    #TODO
    base_path = "../ADS_scans_sample"
    for vol in identify_journals(base_path):
        vol_to_process  = None
        with app.session_scope() as session:
            existing_vol = JournalVolume.get_from_obj(vol, session)
            if existing_vol:
                if vol.file_hash != existing_vol.file_hash:
                        existing_vol.status = VolumeStatus.Update
                        existing_vol.file_hash = vol.file_hash
                        session.add(existing_vol)
                        session.commit()
                        vol_to_process = existing_vol.id
                elif existing_vol.status != VolumeStatus.Done:
                    vol_to_process = existing_vol.id
                    #TODO deal with error and new
            else:
                vol.status = VolumeStatus.New
                session.add(vol)
                session.commit()
                vol_to_process = vol.id
        if vol_to_process:
            task_process_volume.delay(vol_to_process)

if __name__ == '__main__':
    app.start()
