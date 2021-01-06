from airflow.plugins_manager import AirflowPlugin
from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults
from airflow.contrib.hooks.bigquery_hook import BigQueryHook
from googleapiclient.errors import HttpError
from google.cloud import bigquery
from airflow.exceptions import AirflowException
from airflow.sensors.base_sensor_operator import BaseSensorOperator

class BigQueryDataValidationOperator(BaseOperator):
    template_fields = ["sql"]
    ui_color = "#fcf197"

    @apply_defaults
    def __init__(
        self, 
        sql, 
        gcp_conn_id="google_cloud_default", 
        use_legacy_sql=False, 
        location=None, 
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.sql = sql
        self.gcp_conn_id = gcp_conn_id
        self.use_legacy_sql = use_legacy_sql
        self.location = location

    def run_query(self, project, credentials):
        client =  bigquery.Client(project=project, credentials=credentials)
        query_job = client.query(self.sql)
        results = query_job.result()
        return [list(row.values()) for row in results][0]
        
    def execute(self, context):
        # 1. Make connection to BigQuery using BigQueryHook
        hook = BigQueryHook(
            bigquery_conn_id=self.gcp_conn_id,
            use_legacy_sql=self.use_legacy_sql,
            location=self.location
        )
        # 2. Run SQL query
        records = self.run_query(project=hook._get_field("project"), credentials=hook._get_credentials())
        # 3. Call bool() on each value in result record
        if not records:
            raise AirflowException("Query returned no results.")
        elif not all([bool(record) for record in records]):
            raise AirflowException(f"Test failed\nQuery: {self.sql}\nRecords: {records}")
        # 4. Raise exception if any values return False
        self.log.info(f"Test passed\nQuery: {self.sql}\nRecords: {records}")

class BigQueryDatasetSensor(BaseSensorOperator):
    template_fields = ['project_id','dataset_id']
    ui_color = "#feeef1"

    def __init__(self, project_id, dataset_id, gcp_conn_id='google_cloud_default', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.gcp_conn_id = gcp_conn_id

    def poke(self, context):
        # 1. Initialise BigQueryHook
        hook = BigQueryHook(bigquery_conn_id=self.gcp_conn_id)
        # 2. Get BigQuery service object
        service = hook.get_service()
        # 3. Check if dataset exists in a try-except clause
        try:
            service.datasets().get(datasetId = self.dataset_id, projectId=self.project_id).execute()
            return True
        except HttpError as e:
            if e.resp['status'] == '404':
                return False 
            raise AirflowException(f"Error: {e}")

class BigQueryPlugin(AirflowPlugin):
    name = "bigquery_plugin"
    operators = [BigQueryDataValidationOperator]
    sensors = [BigQueryDatasetSensor]