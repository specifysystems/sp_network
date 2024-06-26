"""Class for the Specify Network Name API service."""
from werkzeug.exceptions import BadRequest

from flask_app.common.s2n_type import APIService, AnalystOutput
from flask_app.analyst.base import _AnalystService

from sppy.aws.aws_constants import PROJ_BUCKET
from sppy.tools.provider.spnet import SpNetAnalyses
from sppy.tools.s2n.utils import (combine_errinfo, get_traceback)


# .............................................................................
class RankSvc(_AnalystService):
    """Specify Network API service for retrieving taxonomic information."""
    SERVICE_TYPE = APIService.Rank
    ORDERED_FIELDNAMES = []

    # ...............................................
    @classmethod
    def rank_counts(cls, count_by, order=None, limit=10):
        """Return occurrence and species counts for dataset/organization identifiers.

        Args:
            count_by: URL parameter indicating rank datasets by counts of "species" or
                "occurrence" .
            order: URL parameter indicating whether to rank in "descending" or
                "ascending" order.
            limit: integer URL parameter specifying the number of ordered records to
                return.

            full_output (flask_app.common.s2n_type.AnalystOutput): including records
                as a list of lists (CSV) or dictionaries (JSON) of records
                containing dataset_key,  occurrence count, and species count.

        Returns:
            JSON response for this API query.
        """
        if count_by is None:
            return cls.get_endpoint()

        records = []
        try:
            good_params, errinfo = cls._standardize_params(
                count_by=count_by, order=order, limit=limit)

        except BadRequest as e:
            errinfo = {"error": [e.description]}

        else:
            # Query for ordered dataset counts
            try:
                records, errors = cls._get_ordered_counts(
                    good_params["count_by"], good_params["order"],
                    good_params["limit"])
            except Exception:
                errors = {"error": [get_traceback()]}

            # Combine errors from success or failure
            errinfo = combine_errinfo(errinfo, errors)

        # Assemble
        full_out = AnalystOutput(
            cls.SERVICE_TYPE["name"], description=cls.SERVICE_TYPE["description"],
            output=records, errors=errinfo)

        return full_out.response

    # ...............................................
    @classmethod
    def _get_ordered_counts(cls, count_by, order, limit):
        records = []
        s3 = SpNetAnalyses(PROJ_BUCKET)
        try:
            records, errinfo = s3.rank_dataset_counts(count_by, order, limit)

        except Exception:
            errinfo = {"error": [get_traceback()]}

        return records, errinfo


# .............................................................................
if __name__ == "__main__":
    dataset_key = "0000e36f-d0e9-46b0-aa23-cc1980f00515"

    svc = RankSvc()
    # response = svc.get_endpoint()
    # AnalystOutput.print_output(response, do_print_rec=True)
    count_by = "species"
    order = "descending"
    limit = 5
    response = svc.rank_counts(count_by)
    AnalystOutput.print_output(response, do_print_rec=True)
    # print(response)

"""
from werkzeug.exceptions import BadRequest

from flask_app.common.s2n_type import APIService, AnalystOutput
from flask_app.analyst.base import _AnalystService
from flask_app.analyst.rank import *

from sppy.aws.aws_constants import PROJ_BUCKET
from sppy.tools.provider.spnet import SpNetAnalyses
from sppy.tools.s2n.utils import (combine_errinfo, get_traceback)

dataset_key = "0000e36f-d0e9-46b0-aa23-cc1980f00515"
count_by = "species"
order = "descending"
limit = 5

svc = RankSvc()
response = svc.rank_counts(count_by)
AnalystOutput.print_output(response, do_print_rec=True)

"""
