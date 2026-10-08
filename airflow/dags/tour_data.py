from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator


DEFAULT_ARGS = {"owner": "data", "retries": 3, "retry_delay": timedelta(minutes=10)}


with DAG(
    "tour_data_daily",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 10, 8),
    schedule="15 0 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["tourapi", "daily"],
) as dag:
    collect_images = BashOperator(
        task_id="collect_images",
        pool="tourapi",
        bash_command="cd $PROJECT_ROOT && python src/collect/tour_images.py 930",
    )
    collect_food = BashOperator(
        task_id="collect_food_intro",
        pool="tourapi",
        bash_command="cd $PROJECT_ROOT && python src/collect/tour_food_intro.py",
    )
    collect_festivals = BashOperator(
        task_id="collect_festivals",
        pool="tourapi",
        bash_command=(
            "cd $PROJECT_ROOT && python src/collect/region_context.py festivals "
            "{{ ds_nodash }} {{ macros.ds_format(macros.ds_add(ds, 365), '%Y-%m-%d', '%Y%m%d') }}"
        ),
    )
    publish = BashOperator(
        task_id="publish",
        trigger_rule="none_failed",
        bash_command="cd $PROJECT_ROOT && python src/ingest/publish_tour.py --logical-date {{ ds }}",
    )
    cache_images = BashOperator(
        task_id="cache_images",
        bash_command="cd $PROJECT_ROOT && python src/ingest/cache_images.py",
    )
    [collect_images, collect_food, collect_festivals] >> publish >> cache_images


with DAG(
    "tour_catalog_daily",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 10, 8),
    schedule="45 1 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["tourapi", "catalog"],
) as catalog_dag:
    collect_catalog = BashOperator(
        task_id="collect_catalog",
        pool="tourapi",
        bash_command=(
            "cd $PROJECT_ROOT && for ct in 12 28 39; do "
            "d=data/raw/tourapi/areaBasedList2_ct${ct}_{{ ds_nodash }}; "
            "test -d $d || python src/collect/tour_attractions.py $ct; done"
        ),
    )
    publish_catalog = BashOperator(
        task_id="publish",
        bash_command="cd $PROJECT_ROOT && python src/ingest/publish_tour.py --logical-date {{ ds }}",
    )
    collect_catalog >> publish_catalog
