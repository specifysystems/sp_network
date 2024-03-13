"""Class to query tabular summary Specify Network data in S3"""
import boto3
import json
import pandas as pd

from sppy.aws.aws_tools import get_current_datadate_str
from sppy.aws.aws_constants import (REGION, SUMMARY_FOLDER)
from sppy.tools.s2n.utils import get_traceback



# .............................................................................
class S3Query():
    """Specify Network API service for retrieving tabular parquet data from AWS S3."""

    # ...............................................
    @classmethod
    def __init__(
            self, bucket, region=REGION, encoding="utf-8"):
        """Object to query tabular data in S3.

        Args:
             bucket: S3 bucket containing data.
             s3_path: S3 folder(s) containing data objects.
             datatype: type of tabular data, 'CSV', 'JSON', and 'Parquet' are allowed.
             region: AWS region containing the data.
             encoding: encoding of the data.
        """
        self.s3 = boto3.client('s3')
        self.bucket = bucket
        self.region = region
        self.encoding = encoding
        self._current_datestr = get_current_datadate_str()
        self.exp_type = 'SQL'

    # ----------------------------------------------------
    def _query_s3_table(self, s3_path, query_str, format="JSON"):
        """Query the S3 resource defined for this class.

        Args:
            query_str: a SQL query for S3 select.

        Returns:
             list of records matching the query
        """
        recs = []
        if format not in ("JSON", "CSV"):
            format = "JSON"
        if format == "JSON":
            out_serialization = {"JSON": {}}
        elif format == "CSV":
            out_serialization = {
                "CSV": {
                    "QuoteFields": "ASNEEDED",
                    "FieldDelimiter": ",",
                    "QuoteCharacter": '"'}
            }
        resp = self.s3.select_object_content(
            Bucket=self.bucket,
            Key=s3_path,
            ExpressionType='SQL',
            Expression=query_str,
            InputSerialization={"Parquet": {}},
            OutputSerialization=out_serialization
        )
        for event in resp["Payload"]:
            if "Records" in event:
                recs_str = event["Records"]["Payload"].decode(ENCODING)
                rec_strings = recs_str.split("\n")
                for rs in rec_strings:
                    if rs:
                        if format == "JSON":
                            rec = json.loads(rs)
                        else:
                            rec = rs.split(",")
                        recs.append(rec)
        return recs

    # ----------------------------------------------------
    def _create_dataframe_from_s3obj(self, s3_path):
        """Read CSV data from S3 into a pandas DataFrame.

        Args:
            s3_path: the object name with enclosing S3 bucket folders.

        Returns:
            df: pandas DataFrame containing the CSV data.
        """
        # import pyarrow.parquet as pq
        # import s3fs
        s3_uri = f"s3://{self.bucket}/{s3_path}"
        # s3_fs = s3fs.S3FileSystem
        df = pd.read_parquet(s3_uri)
        return df

    # ----------------------------------------------------
    def _query_order_s3_table(self, s3_path, sort_field, descending, limit):
        """Query the S3 resource defined for this class.

        Args:
            query_str: a SQL query for S3 select.

        Returns:
             list of records matching the query
        """
        recs = []
        errors = {}
        df = self._create_dataframe_from_s3obj(s3_path)
        df.sort_values(by=sort_field, ascending=(not descending))
        for event in resp["Payload"]:
            if "Records" in event:
                records = event["Records"]["Payload"].decode(self.encoding)
                recs.append(records)
        return recs, errors

    # ----------------------------------------------------
    def get_dataset_counts(self, dataset_key):
        """Query the S3 resource for occurrence and species counts for this dataset.

        Args:
            dataset_key: unique GBIF identifier for dataset of interest.

        Returns:
             records: empty list or list of 1 record containing occ_count, species_count
        """
        (occ_count, species_count) = (0,0)
        datestr = get_current_datadate_str()
        datestr = "2024_02_01"
        s3_path = f"{SUMMARY_FOLDER}/dataset_counts_{datestr}_000.parquet"
        query_str = (f"SELECT datasetkey, occ_count, species_count "
                     f"FROM s3object s "
                     f"WHERE s.datasetkey = '{dataset_key}'")
        print(query_str)
        # Returns empty list or list of 1 record with [(occ_count, species_count)]
        records = self._query_s3_table(s3_path, query_str, format="JSON")
        return records

    # ----------------------------------------------------
    def get_org_counts(self, pub_org_key):
        """Query S3 for occurrence and species counts for this organization.

        Args:
            pub_org_key: unique GBIF identifier for organization of interest.

        Returns:
             records: empty list or list of 1 record containing occ_count, species_count

        TODO: implement this?
        """
        (occ_count, species_count) = (0,0)
        return (occ_count, species_count)

    # ----------------------------------------------------
    def rank_datasets_by_species(self, descending=True, limit=10):
        """Return the top or bottom datasets, with counts, ranked by number of species.

        Args:
            descending: boolean value, if true return top X datasets in descending
                order, if false, return bottom X datasets in ascending order
            limit: number of datasets to return, no more than 300.

        Returns:
             records: list of limit records containing dataset_key, occ_count, species_count
        """
        records = []
        datestr = get_current_datadate_str()
        datestr = "2024_02_01"
        s3_path = f"{SUMMARY_FOLDER}/dataset_counts_{datestr}_000.parquet"
        try:
            records, errors = self._query_order_s3_table(
                s3_path, "species_count", descending, limit)
        except Exception as e:
            errors = {"error": get_traceback()}
        return records, errors

# .............................................................................
if __name__ == "__main__":
    from sppy.aws.aws_constants import ENCODING, PROJ_BUCKET, REGION

    datestr = "2024_02_01"
    dataset_key = "0000e36f-d0e9-46b0-aa23-cc1980f00515"
    s3 = boto3.client('s3')

    s3_path = f"{SUMMARY_FOLDER}/dataset_counts_{datestr}_000.parquet"
    query_str = (f"SELECT datasetkey, occ_count, species_count "
                 f"FROM s3object s "
                 f"WHERE s.datasetkey = '{dataset_key}'")
    query_str = f"SELECT datasetkey, occ_count, species_count FROM s3object s LIMIT 5"

    format = "CSV"
    if format == "JSON":
        out_serialization = {"JSON": {}}
    elif format == "CSV":
        out_serialization = {
            "CSV": {
                "QuoteFields": "ASNEEDED",
                "FieldDelimiter": ",",
                "QuoteCharacter": '"'}
        }
    resp = s3.select_object_content(
        Bucket=PROJ_BUCKET,
        Key=s3_path,
        ExpressionType="SQL",
        Expression=query_str,
        InputSerialization={"Parquet": {}},
        OutputSerialization=out_serialization
    )

    for event in resp["Payload"]:
        print(event)
        if "Records" in event:
            recs_str = event["Records"]["Payload"].decode(ENCODING)
            rec_strings = recs_str.split("\n")
            for rs in rec_strings:
                if rs:
                    if format == "JSON":
                        rec = json.loads(rs)
                    else:
                        rec = rs.split(",")
                    print(rec)




    # records = self._query_s3_table(s3_path, query_str)
"""

"""