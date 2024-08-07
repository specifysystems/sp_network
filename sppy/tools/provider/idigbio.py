"""Module containing functions for GBIF API Queries."""
import os

from flask_app.broker.constants import (
    GBIF_MISSING_KEY, Idigbio, ISSUE_DEFINITIONS)
from flask_app.common.s2n_type import APIEndpoint, BrokerSchema, S2nKey, ServiceProvider
from flask_app.common.constants import ENCODING

from sppy.tools.util.logtools import logit
from sppy.tools.util.fileop import ready_filename
from sppy.tools.provider.api import APIQuery
from sppy.tools.util.utils import add_errinfo


# .............................................................................
class IdigbioAPI(APIQuery):
    """Class to query iDigBio APIs and return results."""

    PROVIDER = ServiceProvider.iDigBio
    OCCURRENCE_MAP = BrokerSchema.get_idb_occurrence_map()

    # ...............................................
    def __init__(self, q_filters=None, other_filters=None, filter_string=None,
                 headers=None, logger=None):
        """Constructor.

        Args:
            q_filters: dictionary of filters for the q element of a solr query.
            other_filters: dictionary of other filters.
            filter_string: assembled URL query string.
            headers: any headers to be sent to the server
            logger: object for logging messages and errors.
        """
        idig_search_url = "/".join((
            Idigbio.SEARCH_PREFIX, Idigbio.SEARCH_POSTFIX,
            Idigbio.OCCURRENCE_POSTFIX))
        all_q_filters = {}
        all_other_filters = {}

        if q_filters:
            all_q_filters.update(q_filters)

        if other_filters:
            all_other_filters.update(other_filters)

        APIQuery.__init__(
            self, idig_search_url, q_filters=all_q_filters,
            other_filters=all_other_filters, filter_string=filter_string,
            headers=headers, logger=logger)

    # ...............................................
    @classmethod
    def init_from_url(cls, url, headers=None, logger=None):
        """Initialize from url.

        Args:
            url: Query URL.
            headers: any headers to be sent to the server
            logger: object for logging messages and errors.

        Returns:
            Query object.

        Raises:
            Exception: on failure to initialize object
        """
        base, filters = url.split("?")
        if base.strip().startswith(Idigbio.SEARCH_PREFIX):
            qry = IdigbioAPI(
                filter_string=filters, headers=headers, logger=logger)
        else:
            raise Exception(
                f"iDigBio occurrence API must start with {Idigbio.SEARCH_PREFIX}")
        return qry

    # ...............................................
    def query(self):
        """Queries the API and sets "output" attribute to a JSON object."""
        APIQuery.query_by_post(self, output_type="json")

    # ...............................................
    @classmethod
    def _standardize_record(cls, big_rec):
        newrec = {}
        to_list_fields = ("dwc:associatedSequences", "dwc:associatedReferences")
        issue_fld = "s2n:issues"
        cc_std_fld = "dwc:countryCode"
        view_std_fld = BrokerSchema.get_view_url_fld()
        data_std_fld = BrokerSchema.get_data_url_fld()

        # Outer record must contain "data" and may contain "indexTerms" elements
        try:
            data_elt = big_rec["data"]
        except Exception:
            pass
        else:
            # Pull uuid from outer record
            try:
                uuid = big_rec[Idigbio.ID_FIELD]
            except KeyError:
                print("Record missing uuid field")
                uuid = None

            # Pull indexTerms from outer record
            try:
                idx_elt = big_rec["indexTerms"]
            except KeyError:
                pass
            else:
                # Pull optional "flags" element from "indexTerms"
                try:
                    issue_codes = idx_elt["flags"]
                except KeyError:
                    issue_codes = None
                try:
                    ctry_code = idx_elt["countrycode"]
                except KeyError:
                    ctry_code = None

            # Iterate over desired output fields
            for stdfld, provfld in cls.OCCURRENCE_MAP.items():
                # Include ID fields and issues even if empty
                if provfld == Idigbio.ID_FIELD:
                    newrec[stdfld] = uuid
                    newrec[view_std_fld] = Idigbio.get_occurrence_view(uuid)
                    newrec[data_std_fld] = Idigbio.get_occurrence_data(uuid)

                elif provfld == issue_fld:
                    newrec[stdfld] = cls._get_code2description_dict(
                        issue_codes, ISSUE_DEFINITIONS[ServiceProvider.iDigBio[S2nKey.PARAM]])

                elif stdfld == cc_std_fld:
                    newrec[stdfld] = ctry_code

                else:
                    # all other fields are pulled from data element
                    try:
                        val = data_elt[provfld]
                    except KeyError:
                        val = None

                    if val and provfld in to_list_fields:
                        lst = val.split("|")
                        elts = [item.strip() for item in lst]
                        newrec[stdfld] = elts
                    else:
                        newrec[stdfld] = val
        return newrec

    # ...............................................
    # def query_by_gbif_taxon_id(self, taxon_key):
    def get_occurrences_by_gbif_taxon_id(self, taxon_key):
        """Return a list of occurrence record dictionaries.

        Args:
            taxon_key: GBIF assigned taxonKey

        Returns:
            specimen_list: list of specimen records
        """
        self._q_filters[Idigbio.GBIFID_FIELD] = taxon_key
        self.query()
        specimen_list = []
        if self.output is not None:
            # full_count = self.output["itemCount"]
            for item in self.output[Idigbio.RECORDS_KEY]:
                new_item = item[Idigbio.RECORD_CONTENT_KEY].copy()

                for idx_fld, idx_val in item[Idigbio.RECORD_INDEX_KEY].items():
                    if idx_fld == "geopoint":
                        new_item["dec_long"] = idx_val["lon"]
                        new_item["dec_lat"] = idx_val["lat"]
                    else:
                        new_item[idx_fld] = idx_val
                specimen_list.append(new_item)
        return specimen_list

    # ...............................................
    # def query_by_gbif_taxon_id(self, taxon_key):
    def count_occurrences_by_gbif_taxon_id(self, taxon_key):
        """Return a count of occurrence records with the GBIF taxonKey.

        Args:
            taxon_key: GBIF assigned taxonKey

        Returns:
            full_count: count of specimen records
        """
        self._q_filters[Idigbio.GBIFID_FIELD] = taxon_key
        self.query()
        if self.output is not None:
            full_count = self.output["itemCount"]
        return full_count

    # ...............................................
    @classmethod
    def get_occurrences_by_occid(cls, occid, count_only=False, logger=None):
        """Return iDigBio occurrences for this occurrenceId.

        Args:
            occid: occurrenceID for record to return.
            count_only: True to only return a count of matching records
            logger: object for logging messages and errors.

        Returns:
            a flask_app.broker.s2n_type.S2nOutput object

        Todo: enable paging
        """
        errinfo = {}
        qf = {Idigbio.QKEY:
              '{"' + Idigbio.OCCURRENCEID_FIELD + '":"' + occid + '"}'}
        api = IdigbioAPI(other_filters=qf, logger=logger)

        try:
            api.query()
        except Exception:
            std_out = cls._get_query_fail_output(
                [api.url], APIEndpoint.Occurrence)
        else:
            errinfo = add_errinfo(errinfo, "error", api.error)
            prov_meta = cls._get_provider_response_elt(
                query_status=api.status_code, query_urls=[api.url])
            std_out = cls._standardize_output(
                api.output, Idigbio.COUNT_KEY, Idigbio.RECORDS_KEY,
                Idigbio.RECORD_FORMAT, APIEndpoint.Occurrence, prov_meta,
                count_only=count_only, errinfo=errinfo)

        return std_out

    # ...............................................
    @classmethod
    def _write_idigbio_metadata(cls, orig_fld_names, meta_f_name):
        pass

    # ...............................................
    @classmethod
    def _get_idigbio_fields(cls, rec):
        # Get iDigBio fields
        fld_names = list(rec["indexTerms"].keys())
        # add dec_long and dec_lat to records
        fld_names.extend(["dec_lat", "dec_long"])
        fld_names.sort()
        return fld_names

#     # ...............................................
#     @classmethod
#     def _count_idigbio_records(cls, gbif_taxon_id):
#         """Count iDigBio records for a GBIF taxon id.
#         """
#         api = idigbio.json()
#         record_query = {
#             "taxonid": str(gbif_taxon_id), "geopoint": {"type": "exists"}}
#
#         try:
#             output = api.search_records(rq=record_query, limit=1, offset=0)
#         except Exception:
#             log_info("Failed on {}".format(gbif_taxon_id))
#             total = 0
#         else:
#             total = output["itemCount"]
#         return total
#
#     # ...............................................
#     def _get_idigbio_records(self, gbif_taxon_id, fields, writer,
#                              meta_output_file):
#         """Get records from iDigBio
#         """
#         api = idigbio.json()
#         limit = 100
#         offset = 0
#         curr_count = 0
#         total = 0
#         record_query = {"taxonid": str(gbif_taxon_id),
#                         "geopoint": {"type": "exists"}}
#         while offset <= total:
#             try:
#                 output = api.search_records(
#                     rq=record_query, limit=limit, offset=offset)
#             except Exception:
#                 log_info("Failed on {}".format(gbif_taxon_id))
#                 total = 0
#             else:
#                 total = output["itemCount"]
#
#                 # First gbifTaxonId where this data retrieval is successful,
#                 # get and write header and metadata
#                 if total > 0 and fields is None:
#                     log_info("Found data, writing data and metadata")
#                     fields = self._get_idigbio_fields(output["items"][0])
#                     # Write header in datafile
#                     writer.writerow(fields)
#                     # Write metadata file with column indices
#                     _meta = self._write_idigbio_metadata(
#                         fields, meta_output_file)
#
#                 # Write these records
#                 recs = output["items"]
#                 curr_count += len(recs)
#                 log_info(("  Retrieved {} records, {} recs starting at {}".format(
#                     len(recs), limit, offset)))
#                 for rec in recs:
#                     rec_data = rec["indexTerms"]
#                     vals = []
#                     for fld_name in fields:
#                         # Pull long, lat from geopoint
#                         if fld_name == "dec_long":
#                             try:
#                                 vals.append(rec_data["geopoint"]["lon"])
#                             except KeyError:
#                                 vals.append("")
#                         elif fld_name == "dec_lat":
#                             try:
#                                 vals.append(rec_data["geopoint"]["lat"])
#                             except KeyError:
#                                 vals.append("")
#                         # or just append verbatim
#                         else:
#                             try:
#                                 vals.append(rec_data[fld_name])
#                             except KeyError:
#                                 vals.append("")
#
#                     writer.writerow(vals)
#                 offset += limit
#         log_info(("Retrieved {} of {} reported records for {}".format(
#             curr_count, total, gbif_taxon_id)))
#         return curr_count, fields

    # ...............................................
    def assemble_idigbio_data(
            self, taxon_ids, point_output_file, meta_output_file,
            missing_id_file=None, logger=None):
        """Assemble iDigBio data dictionary.

        Args:
            taxon_ids: list of taxon_ids to return records for.
            point_output_file: destination file for output records.
            meta_output_file: destination file for output metadata
            missing_id_file: destination file for output of taxonids where no records
                were found.
            logger: object for logging messages and errors.

        Returns:
            report: dictionary of processing metadata.
        """
        if not isinstance(taxon_ids, list):
            taxon_ids = [taxon_ids]

        # Delete old files
        for fname in (point_output_file, meta_output_file):
            if os.path.exists(fname):
                logit(
                    logger, f"Deleting existing file {fname} ...",
                    refname=self.__class__.__name__)
                os.remove(fname)

        report = {GBIF_MISSING_KEY: []}

        ready_filename(point_output_file, overwrite=True)
        with open(point_output_file, "w", encoding=ENCODING, newline=""):
            # writer = csv.writer(csv_f, delimiter=DATA_DUMP_DELIMITER)
            # fld_names = None
            for gid in taxon_ids:
                # Pull / write field names first time
                # pt_count, fld_names = self._get_idigbio_records(
                #     gid, fld_names, writer, meta_output_file)
                recs = self.get_occurrences_by_gbif_taxon_id(gid)
                pt_count = len(recs)

                report[gid] = pt_count
                if pt_count == 0:
                    report[GBIF_MISSING_KEY].append(gid)
                report[gid] = len(recs)

        # get/write missing data
        if missing_id_file is not None and len(
                report[GBIF_MISSING_KEY]) > 0:
            with open(missing_id_file, "w", encoding=ENCODING) as out_f:
                for gid in report[GBIF_MISSING_KEY]:
                    out_f.write(f"{gid}\n")

        return report

    # ...............................................
    def query_idigbio_data(self, taxon_ids):
        """Query iDigBio for data.

        Args:
            taxon_ids: list of GBIF taxonIDs for querying

        Returns:
            report: dictionary of processing metadata.
        """
        if not isinstance(taxon_ids, list):
            taxon_ids = [taxon_ids]

        summary = {GBIF_MISSING_KEY: []}

        for gid in taxon_ids:
            # Pull/write fieldnames first time
            pt_count = self.count_occurrences_by_gbif_taxon_id(gid)
            if pt_count == 0:
                summary[GBIF_MISSING_KEY].append(gid)
            summary[gid] = pt_count

        return summary
