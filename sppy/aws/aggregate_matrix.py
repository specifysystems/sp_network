"""Tools to compute dataset x species statistics from S3 data."""
import boto3
from botocore.exceptions import ClientError, SSLError
import json
from logging import ERROR, INFO
import numpy as np
import os
import pandas as pd
from pandas.api.types import CategoricalDtype
import random
import scipy.sparse
from zipfile import ZipFile

from sppy.aws.aws_constants import (
    LOCAL_OUTDIR, PROJ_BUCKET, REGION, SNKeys, SUMMARY_FOLDER,
    Summaries, SUMMARY_TABLE_TYPES
)
from sppy.aws.aws_tools import (
    download_from_s3, get_current_datadate_str, get_today_str,
    read_s3_parquet_to_pandas
)
from sppy.tools.util.logtools import Logger, logit
from sppy.tools.s2n.utils import convert_np_vals_for_json


# ...............................................
def get_extreme_val_and_attrs_for_column_from_stacked_data(
        stacked_df, filter_label, filter_value, attr_label, val_label, is_max=True):
    """Find the minimum or maximum value for rows where 'filter_label' = 'filter_value'.

    Args:
        stacked_df: dataframe containing stacked data records
        filter_label: column name for filtering.
        filter_value: column value for filtering.
        attr_label: column name of attribute to return.
        val_label: column name for attribute with min/max value.
        is_max (bool): flag indicating whether to get maximum (T) or minimum (F)

    Returns:
        target_val:  Minimum or maximum value for rows where
            'filter_label' = 'filter_value'.
        attr_vals: values for attr_label for rows with the minimum or maximum value.

    Raises:
        Exception: on min/max = 0.  Zeros should never be returned for min or max value.
    """
    # Create a dataframe of rows where column 'filter_label' = 'filter_value'.
    tmp_df = stacked_df.loc[stacked_df[filter_label] == filter_value]
    # Find the min or max value for those rows
    if is_max is True:
        target_val = tmp_df[val_label].max()
    else:
        target_val = tmp_df[val_label].min()
        # There should be NO zeros in these aggregated records
    if target_val == 0:
        raise Exception(
            f"Found value 0 in column {val_label} for rows where "
            f"{filter_label} == {filter_value}")
    # Get the attribute(s) in the row(s) with the max value
    attrs_containing_max_df = tmp_df.loc[tmp_df[val_label] == target_val]
    attr_vals = [rec for rec in attrs_containing_max_df[attr_label]]
    return target_val, attr_vals


# ...............................................
def sum_stacked_data_vals_for_column(stacked_df, filter_label, filter_value, val_label):
    """Sum the values for rows where column 'filter_label' = 'filter_value'.

    Args:
        stacked_df: dataframe containing stacked data records
        filter_label: column name for filtering.
        filter_value: column value for filtering.
        val_label: column name for summation.

    Returns:
        tmp_df: dataframe containing only rows with a value of filter_value in column
            filter_label.
    """
    # Create a dataframe of rows where column 'filter_label' = 'filter_value'.
    tmp_df = stacked_df.loc[stacked_df[filter_label] == filter_value]
    # Sum the values for those rows
    count = tmp_df[val_label].sum()
    return count


# ...............................................
def test_row_col_comparisons(agg_sparse_mtx, test_count=5, logger=None):
    """Test row comparisons between 1 and all, and column comparisons between 1 and all.

    Args:
        agg_sparse_mtx (SparseMatrix): object containing a scipy.sparse.coo_array
            with 3 columns from the stacked_df arranged as rows and columns with values
        test_count (int): number of rows and columns to test.
        logger (object): logger for saving relevant processing messages

    Postcondition:
        Printed information for successful or failed tests.

    Note: The aggregate_df must have been created from the stacked_df.
    """
    y_vals = agg_sparse_mtx.get_random_labels(test_count, axis=0)
    x_vals = agg_sparse_mtx.get_random_labels(test_count, axis=1)
    for y in y_vals:
        row_comps = agg_sparse_mtx.compare_row_to_others(y)
        logit(logger, "Row comparisons:", print_obj=row_comps)
    for x in x_vals:
        col_comps = agg_sparse_mtx.compare_column_to_others(x)
        logit(logger, "Column comparisons:", print_obj=col_comps)


# ...............................................
def test_stacked_to_aggregate_sum(
        stk_df, stk_axis_col_label, stk_val_col_label, agg_sparse_mtx, agg_axis=0,
        test_count=5, logger=None):
    """Test for equality of sums in stacked and aggregated dataframes.

    Args:
        stk_df: dataframe of stacked data, containing records with columns of
            categorical values and counts.
        stk_axis_col_label: column label in stacked dataframe to be used as the column
            labels of the axis in the aggregate sparse matrix.
        stk_val_col_label: column label in stacked dataframe for data to be used as
            value in the aggregate sparse matrix.
        agg_sparse_mtx (SparseMatrix): object containing a scipy.sparse.coo_array
            with 3 columns from the stacked_df arranged as rows and columns with values]
        agg_axis (int): Axis 0 (row) or 1 (column) that corresponds with the column
            label (stk_axis_col_label) in the original stacked data.
        test_count (int): number of rows and columns to test.
        logger (object): logger for saving relevant processing messages

    Postcondition:
        Printed information for successful or failed tests.

    Note: The aggregate_df must have been created from the stacked_df.
    """
    labels = agg_sparse_mtx.get_random_labels(test_count, axis=agg_axis)
    # Test stacked column totals against aggregate x columns
    for lbl in labels:
        stk_sum = sum_stacked_data_vals_for_column(
            stk_df, stk_axis_col_label, lbl, stk_val_col_label)
        agg_sum = agg_sparse_mtx.sum_vector(lbl, axis=agg_axis)
        logit(logger, f"Test axis {agg_axis}: {lbl}")
        if stk_sum == agg_sum:
            logit(
                logger, f"  Total {stk_sum}: Stacked data for "
                f"{stk_axis_col_label} == aggregate data in axis {agg_axis}: {lbl}"
            )
        else:
            logit(
                logger, f"  !!! {stk_sum} != {agg_sum}: Stacked data for "
                f"{stk_axis_col_label} != aggregate data in axis {agg_axis}: {lbl}"
            )
        logit(logger, "")
    logit(logger, "")


# ...............................................
def test_stacked_to_aggregate_extremes(
        stk_df, stk_col_label_for_axis0, stk_col_label_for_axis1, stk_col_label_for_val,
        agg_sparse_mtx, agg_axis=0, test_count=5, logger=None, is_max=True):
    """Test min/max counts for attributes in the sparse matrix vs. the stacked data.

    Args:
        stk_df: dataframe of stacked data, containing records with columns of
            categorical values and counts.
        stk_col_label_for_axis0: column label in stacked dataframe to be used as the
            row (axis 0) labels of the axis in the aggregate sparse matrix.
        stk_col_label_for_axis1: column label in stacked dataframe to be used as the
            column (axis 1) labels of the axis in the aggregate sparse matrix.
        stk_col_label_for_val: column label in stacked dataframe for data to be used as
            value in the aggregate sparse matrix.
        agg_sparse_mtx (SparseMatrix): object containing a scipy.sparse.coo_array
            with 3 columns from the stacked_df arranged as rows and columns with values]
        agg_axis (int): Axis 0 (row) or 1 (column) that corresponds with the column
            label (stk_axis_col_label) in the original stacked data.
        test_count (int): number of rows and columns to test.
        logger (object): logger for saving relevant processing messages
        is_max (bool): flag indicating whether to test maximum (T) or minimum (F)

    Postcondition:
        Printed information for successful or failed tests.

    Note: The aggregate_df must have been created from the stacked_df.
    """
    labels = agg_sparse_mtx.get_random_labels(test_count, axis=agg_axis)
    # for logging
    if is_max is True:
        extm = "Max"
    else:
        extm = "Min"

    # Get min/max of row (identified by filter_label, attr_label in axis 0)
    if agg_axis == 0:
        filter_label, attr_label = stk_col_label_for_axis0, stk_col_label_for_axis1
    # Get min/max of column (identified by label in axis 1)
    elif agg_axis == 1:
        filter_label, attr_label = stk_col_label_for_axis1, stk_col_label_for_axis0

    # Test dataset - get species with largest count and compare
    for lbl in labels:
        (stk_target_val,
         stk_attr_vals) = get_extreme_val_and_attrs_for_column_from_stacked_data(
            stk_df, filter_label, lbl, attr_label, stk_col_label_for_val, is_max=is_max)
        agg_target_val, agg_labels = agg_sparse_mtx.get_extreme_val_labels_for_vector(
            lbl, axis=agg_axis, is_max=is_max)
        logit(logger, f"Test vector {lbl} on axis {agg_axis}")
        if stk_target_val == agg_target_val:
            logit(logger, f"  {extm} values equal {stk_target_val}")
            if set(stk_attr_vals) == set(agg_labels):
                logit(
                    logger, f"  {extm} value labels equal; "
                    f"len={len(stk_attr_vals)}")
            else:
                logit(
                    logger, f"  !!! {extm} value labels NOT equal; "
                    f"stacked labels {stk_attr_vals} != agg labels {agg_labels}"
                )
        else:
            logit(
                logger, f"!!! {extm} stacked value {stk_target_val} != "
                f"{agg_target_val} agg value")
        logit(logger, "")
    logit(logger, "")


# .............................................................................
# .............................................................................
class SparseMatrix:
    """Class for managing computations for counts of aggregator0 x aggregator1."""

    # ...........................
    def __init__(
            self, sparse_coo_array, table_type, data_datestr, row_category=None,
            column_category=None, logger=None):
        """Constructor for species by dataset comparisons.

        Args:
            sparse_coo_array (scipy.sparse.coo_array): A 2d sparse array with count
                values for one aggregator0 (i.e. species) rows (axis 0) by another
                aggregator1 (i.e. dataset) columns (axis 1) to use for computations.
            table_type (aws_constants.SUMMARY_TABLE_TYPES): type of aggregated data
            data_datestr (str): date of the source data in YYYY_MM_DD format.
            row_category (CategoricalDtype): category of unique labels with ordered
                indices/codes for rows (y, axis 0)
            column_category (CategoricalDtype): category of unique labels with ordered
                indices/codes for columns (x, axis 1)
            logger (object): An optional local logger to use for logging output
                with consistent options

        Note: in the first implementation, because species are generally far more
            numerous, rows are always species, columns are datasets.  This allows
            easier exporting to other formats (i.e. Excel), which allows more rows than
            columns.
        """
        self._coo_array = sparse_coo_array
        self._table_type = table_type
        self._data_datestr = data_datestr
        self._keys = SNKeys.get_keys_for_table(self._table_type)
        self._row_categ = row_category
        self._col_categ = column_category
        self._logger = logger
        self._report = {}

    # ...........................
    @classmethod
    def init_from_stacked_data(
            cls, stacked_df, x_fld, y_fld, val_fld, table_type, data_datestr,
            logger=None):
        """Create a sparse matrix of rows by columns containing values from a table.

        Args:
            stacked_df (pandas.DataFrame): DataFrame of records containing columns to be
                used as the new rows, new columns, and values.
            x_fld: column in the input dataframe containing values to be used as
                columns (axis 1)
            y_fld: column in the input dataframe containing values to be used as rows
                (axis 0)
            val_fld: : column in the input dataframe containing values to be used as
                values for the intersection of x and y fields
            table_type (aws_constants.SUMMARY_TABLE_TYPES): table type of sparse matrix
                aggregated data
            data_datestr (str): date of the source data in YYYY_MM_DD format.
            logger (object): logger for saving relevant processing messages

        Returns:
            sparse_coo (scipy.coo_array): matrix of y values (rows, y axis=0) by
                x values (columnns, x axis=1), with values from another column.

        Note:
            The input dataframe must contain only one input record for any x and y value
                combination, and each record must contain another value for the dataframe
                contents.  The function was written for a table of records with
                datasetkey (for the column labels/x), species (for the row labels/y),
                and occurrence count.
        """
        # Get unique values to use as categories for scipy column and row indexes, remove None
        unique_x_vals = list(stacked_df[x_fld].dropna().unique())
        unique_y_vals = list(stacked_df[y_fld].dropna().unique())
        # Categories allow using codes as the integer index for scipy matrix
        y_categ = CategoricalDtype(unique_y_vals, ordered=True)
        x_categ = CategoricalDtype(unique_x_vals, ordered=True)
        # Create a list of category codes matching original stacked data records to replace
        #   column names from stacked data dataframe with integer codes for row and column
        #   indexes in the new scipy matrix
        col_idx = stacked_df[x_fld].astype(x_categ).cat.codes
        row_idx = stacked_df[y_fld].astype(y_categ).cat.codes
        # This creates a new matrix in Coordinate list (COO) format.  COO stores a list of
        # (row, column, value) tuples.  Convert to CSR or CSC for efficient Row or Column
        # slicing, respectively
        sparse_coo = scipy.sparse.coo_array(
            (stacked_df[val_fld], (row_idx, col_idx)),
            shape=(y_categ.categories.size, x_categ.categories.size))
        sparse_matrix = SparseMatrix(
            sparse_coo, table_type, data_datestr, row_category=y_categ,
            column_category=x_categ, logger=logger)
        return sparse_matrix

    # .............................................................................
    def _to_dataframe(self):
        sdf = pd.DataFrame.sparse.from_spmatrix(
            self._coo_array,
            index=self._row_categ.categories,
            columns=self._col_categ.categories)
        return sdf

    # ...............................................
    def _get_code_from_category(self, label, axis=0):
        if axis == 0:
            categ = self._row_categ
        elif axis == 1:
            categ = self._col_categ
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")

        # returns a tuple of a single 1-dimensional array of locations
        arr = np.where(categ.categories == label)[0]
        try:
            # labels are unique in categories so there will be 0 or 1 value in the array
            code = arr[0]
        except IndexError:
            raise Exception(f"Category {label} does not exist in axis {axis}")
        return code

    # ...............................................
    def _get_category_from_code(self, code, axis=0):
        if axis == 0:
            categ = self._row_categ
        elif axis == 1:
            categ = self._col_categ
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")
        category = categ.categories[code]
        return category

    # ...............................................
    def _export_categories(self, axis=0):
        if axis == 0:
            categ = self._row_categ
        elif axis == 1:
            categ = self._col_categ
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")
        cat_lst = categ.categories.tolist()
        return cat_lst

    # ...............................................
    def _get_categories_from_code(self, code_list, axis=0):
        if axis == 0:
            categ = self._row_categ
        elif axis == 1:
            categ = self._col_categ
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")
        category_labels = []
        for code in code_list:
            category_labels.append(categ.categories[code])
        return category_labels

    # ...............................................
    def _logme(self, msg, refname="", log_level=None):
        logit(self._logger, msg, refname=refname, log_level=log_level)

    # ...........................
    def _to_csr(self):
        # Convert to CSR format for efficient row slicing
        csr = self._coo_array.tocsr()
        return csr

    # ...........................
    def _to_csc(self):
        # Convert to CSC format for efficient column slicing
        csc = self._coo_array.tocsr()
        return csc

    # ...............................................
    def get_random_labels(self, count, axis=0):
        """Get random values from the labels on an axis of a sparse matrix.

        Args:
            count (int): number of values to return
            axis (int): column (0) or row (1) header for labels to gather.

        Returns:
            x_vals (list): random values pulled from the column

        Raises:
            Exception: on axis not in (0, 1)
        """
        if axis == 0:
            categ = self._row_categ
        elif axis == 1:
            categ = self._col_categ
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")
        # Get a random sample of category indexes
        idxs = random.sample(range(1, len(categ.categories)), count)
        labels = [self._get_category_from_code(i, axis=axis) for i in idxs]
        return labels

    # ...............................................
    @property
    def num_y_values(self):
        """Get the number of rows.

        Returns:
            int: The count of rows where the value > 0 in at least one column.

        Note:
            Also used as gamma diversity (species richness over entire landscape)
        Note: because the sparse data will only from contain unique rows and columns
            with data, this should ALWAYS equal the number of rows
        """
        return self._coo_array.shape[0]

    # ...............................................
    @property
    def num_x_values(self):
        """Get the number of columns.

        Returns:
            int: The count of columns where the value > 0 in at least one row

        Note: because the sparse data will only from contain unique rows and columns
            with data, this should ALWAYS equal the number of columns
        """
        return self._coo_array.shape[1]

    # ...............................................
    def get_vector_from_label(self, label, axis=0):
        """Return the row (axis 0) or column (axis 1) with label `label`.

        Args:
            label: label for row of interest
            axis (int): column (0) or row (1) header for vector and index to gather.

        Returns:
            vector (scipy.sparse.csr_array): 1-d array of the row/column for 'label'.
            idx (int): index for the vector (zeros and non-zeros) in the sparse matrix

        Raises:
            Exception: on axis not in (0, 1)
        """
        idx = self._get_code_from_category(label, axis=axis)
        if axis == 0:
            vector = self._coo_array.getrow(idx)
        elif axis == 1:
            vector = self._coo_array.getcol(idx)
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")
        return vector, idx

    # ...............................................
    def sum_vector(self, label, axis=0):
        """Get the total of values in a single row or column.

        Args:
            label: label on the row (axis 0) or column (axis 1) to total.
            axis (int): column (0) or row (1) header for vector to sum.

        Returns:
            int: The total of all values in one column
        """
        vector, _idx = self.get_vector_from_label(label, axis=axis)
        total = vector.sum()
        return total

    # ...............................................
    def get_row_labels_for_data_in_column(self, col, value=None):
        """Get the minimum or maximum NON-ZERO value and row label(s) for a column.

        Args:
            col: column to find row labels in.
            value: filter data value to return row labels for.  If None, return labels
                for all non-zero rows.

        Returns:
            target: The minimum or maximum value for a column
            row_labels: The labels of the rows containing the target value
        """
        # Returns row_idxs, col_idxs, vals of NNZ values in row
        row_idxs, col_idxs, vals = scipy.sparse.find(col)
        if value is None:
            idxs_lst = [row_idxs[i] for i in range(len(row_idxs))]
        else:
            tmp_idxs = np.where(vals == value)[0]
            tmp_idx_lst = [tmp_idxs[i] for i in range(len(tmp_idxs))]
            # Row indexes of maxval in column
            idxs_lst = [row_idxs[i] for i in tmp_idx_lst]
        row_labels = [self._get_category_from_code(idx, axis=0) for idx in idxs_lst]
        return row_labels

    # ...............................................
    def get_extreme_val_labels_for_vector(self, label, axis=0, is_max=True):
        """Get the minimum or maximum NON-ZERO value and row label(s) for a column.

        Args:
            label: label on the row(0)/column(1) to find minimum or maximum.
            is_max (bool): flag indicating whether to get maximum (T) or minimum (F)
            axis (int): row (0) or column (1) header for extreme value and labels.

        Returns:
            target: The minimum or maximum value for a column
            row_labels: The labels of the rows containing the target value

        Raises:
            Exception: on axis not in (0, 1)
        """
        vector, _idx = self.get_vector_from_label(label, axis=axis)
        # Returns row_idxs, col_idxs, vals of NNZ values in row
        row_idxs, col_idxs, vals = scipy.sparse.find(vector)
        if is_max is True:
            target = vals.max()
        else:
            target = vals.min()
        target = convert_np_vals_for_json(target)

        # Get indexes of target value within NNZ vals
        tmp_idxs = np.where(vals == target)[0]
        tmp_idx_lst = [tmp_idxs[i] for i in range(len(tmp_idxs))]
        # Get actual indexes (within all zero/non-zero elements) of target in vector
        if axis == 0:
            # Column indexes of maxval in row
            idxs_lst = [col_idxs[i] for i in tmp_idx_lst]
            # Label axis is the opposite of the vector axis
            label_axis = 1
        elif axis == 1:
            # Row indexes of maxval in column
            idxs_lst = [row_idxs[j] for j in tmp_idx_lst]
            label_axis = 0
        else:
            raise Exception(f"2D sparse array does not have axis {axis}")

        # Convert from indexes to labels
        labels = [
            self._get_category_from_code(idx, axis=label_axis) for idx in idxs_lst]
        return target, labels

    # ...............................................
    def get_all_row_stats(self):
        """Return stats (min, max, mean, median) of totals and counts for all rows.

        Returns:
            all_row_stats (dict): counts and statistics about all rows.
            (numpy.ndarray): array of totals of all rows.
        """
        # Sum all rows to return a column (axis=1)
        all_totals = self._coo_array.sum(axis=1)
        # Get number of non-zero entries for every row (column, numpy.ndarray)
        all_counts = self._coo_array.getnnz(axis=1)
        # Count columns with at least one non-zero entry (all columns)
        row_count = self._coo_array.shape[1]
        all_row_stats = {
            self._keys[SNKeys.ROWS_COUNT]: row_count,
            self._keys[SNKeys.ROWS_TOTAL]: convert_np_vals_for_json(all_totals.sum()),
            self._keys[SNKeys.ROWS_MIN]: convert_np_vals_for_json(all_totals.min()),
            self._keys[SNKeys.ROWS_MAX]: convert_np_vals_for_json(all_totals.max()),
            self._keys[SNKeys.ROWS_MEAN]: convert_np_vals_for_json(all_totals.mean()),
            self._keys[SNKeys.ROWS_MEDIAN]: convert_np_vals_for_json(
                np.median(all_totals, axis=0)[0, 0]),

            self._keys[SNKeys.ROWS_COUNT_MIN]: convert_np_vals_for_json(all_counts.min()),
            self._keys[SNKeys.ROWS_COUNT_MAX]: convert_np_vals_for_json(all_counts.max()),
            self._keys[SNKeys.ROWS_COUNT_MEAN]: convert_np_vals_for_json(all_counts.mean()),
            self._keys[SNKeys.ROWS_COUNT_MEDIAN]: convert_np_vals_for_json(
                np.median(all_counts, axis=0)),
        }
        return all_row_stats

    # ...............................................
    def get_all_col_stats(self):
        """Return stats (min, max, mean, median) of totals and counts for all columns.

        Returns:
            all_col_stats (dict): counts and statistics about all columns.
        """
        # Sum all columns to return a row (numpy.ndarray, axis=0)
        all_totals = self._coo_array.sum(axis=0)
        # Get number of non-zero entries for every column (row, numpy.ndarray)
        all_counts = self._coo_array.getnnz(axis=0)
        # Count rows with at least one non-zero entry (all rows)
        col_count = self._coo_array.shape[0]
        all_col_stats = {
            self._keys[SNKeys.COLS_COUNT]: col_count,
            self._keys[SNKeys.COLS_TOTAL]: convert_np_vals_for_json(all_totals.sum()),
            self._keys[SNKeys.COLS_MIN]: convert_np_vals_for_json(all_totals.min()),
            self._keys[SNKeys.COLS_MAX]: convert_np_vals_for_json(all_totals.max()),
            self._keys[SNKeys.COLS_MEAN]: convert_np_vals_for_json(all_totals.mean()),
            self._keys[SNKeys.COLS_MEDIAN]:
                convert_np_vals_for_json(np.median(all_totals, axis=1)[0, 0]),

            self._keys[SNKeys.COLS_COUNT_MIN]:
                convert_np_vals_for_json(all_counts.min()),
            self._keys[SNKeys.COLS_COUNT_MAX]:
                convert_np_vals_for_json(all_counts.max()),
            self._keys[SNKeys.COLS_COUNT_MEAN]:
                convert_np_vals_for_json(all_counts.mean()),
            self._keys[SNKeys.COLS_COUNT_MEDIAN]:
                convert_np_vals_for_json(np.median(all_counts, axis=0)),
        }
        return all_col_stats

    # ...............................................
    def get_column_stats(self, col_label, agg_type=None):
        """Get a dictionary of statistics for the column with this col_label.

        Args:
            col_label: label on the column to gather stats for.
            agg_type: return stats on rows or values.  If None, return both.
                (options: "axis", "value", None)

        Returns:
            stats (dict): quantitative measures of the column.

        Note:
            Inline comments are specific to a SUMMARY_TABLE_TYPES.SPECIES_DATASET_MATRIX
                with row/column/value = species/dataset/occ_count
        """
        # Get column (sparse array), and its index
        col, col_idx = self.get_vector_from_label(col_label, axis=1)
        stats = {
            self._keys[SNKeys.COL_IDX]: col_idx,
            self._keys[SNKeys.COL_LABEL]: col_label,
        }
        if agg_type in ("axis", None):
            # Count of Species within this Dataset
            stats[self._keys[SNKeys.COL_COUNT]] = convert_np_vals_for_json(col.nnz)
        if agg_type in ("value", None):
            # Largest/smallest occ count for dataset (column), and species (row)
            # containing that count
            maxval, max_col_labels = self.get_extreme_val_labels_for_vector(
                col_label, axis=1, is_max=True)
            minval, min_col_labels = self.get_extreme_val_labels_for_vector(
                col_label, axis=1, is_max=False)

            # Total Occurrences for Dataset
            stats[self._keys[SNKeys.COL_TOTAL]] = convert_np_vals_for_json(col.sum())
            # Return min occurrence count in this dataset
            stats[self._keys[SNKeys.COL_MIN_COUNT]] = convert_np_vals_for_json(minval)
            # Return number of species containing same minimum count (too many to list)
            stats[self._keys[SNKeys.COL_MIN_LABELS]] = len(min_col_labels)
            # Return max occurrence count in this dataset
            stats[self._keys[SNKeys.COL_MAX_COUNT]] = convert_np_vals_for_json(maxval)
            # Return species containing same maximum count
            stats[self._keys[SNKeys.COL_MAX_LABELS]] = max_col_labels
        return stats

    # ...............................................
    def get_column_counts(self, col_label, agg_type=None):
        """Get a dictionary of statistics for the column with this col_label.

        Args:
            col_label: label on the column to gather stats for.
            agg_type: return stats on rows or values.  If None, return both.
                (options: "axis", "value", None)

        Returns:
            stats (dict): quantitative measures of the column.

        Note:
            Inline comments are specific to a SUMMARY_TABLE_TYPES.SPECIES_DATASET_MATRIX
                with row/column/value = species/dataset/occ_count
        """
        # Get column (sparse array), and its index
        col, col_idx = self.get_vector_from_label(col_label, axis=1)
        # Largest occ count for dataset (column), species (row) containing that count
        maxval, max_col_labels = self.get_extreme_val_labels_for_vector(
            col_label, axis=1, is_max=True)
        minval, min_col_labels = self.get_extreme_val_labels_for_vector(
            col_label, axis=1, is_max=False)

        stats = {
            self._keys[SNKeys.COL_IDX]: col_idx,
            self._keys[SNKeys.COL_LABEL]: col_label,
            # Total Occurrences for Dataset
            self._keys[SNKeys.COL_TOTAL]: convert_np_vals_for_json(col.sum()),
            # Count of Species within this Dataset
            self._keys[SNKeys.COL_COUNT]: convert_np_vals_for_json(col.nnz),
            # Return min/max count in this dataset and species for that count
            self._keys[SNKeys.COL_MIN_COUNT]: minval,
            # self._keys[SNKeys.COL_MIN_LABELS]: min_col_labels,
            self._keys[SNKeys.COL_MAX_COUNT]: maxval,
            # self._keys[SNKeys.COL_MAX_LABELS]: max_col_labels,
        }
        return stats

    # ...............................................
    def get_row_stats(self, row_label):
        """Get a dictionary of statistics for the row with this row_label.

        Args:
            row_label: label on the row to gather stats for.

        Returns:
            stats (dict): quantitative measures of the row.

        Note:
            Inline comments are specific to a SUMMARY_TABLE_TYPES.SPECIES_DATASET_MATRIX
                with row/column/value = species/dataset/occ_count
        """
        # Get row (sparse array), and its index
        row, row_idx = self.get_vector_from_label(row_label, axis=0)
        # Largest Occurrence count for this Species, and datasets that contain it
        maxval, max_row_labels = self.get_extreme_val_labels_for_vector(
            row_label, axis=0, is_max=True)
        minval, min_row_labels = self.get_extreme_val_labels_for_vector(
            row_label, axis=0, is_max=False)
        stats = {
            self._keys[SNKeys.ROW_IDX]: row_idx,
            self._keys[SNKeys.ROW_LABEL]: row_label,
            # Total Occurrences for this Species
            self._keys[SNKeys.ROW_TOTAL]: convert_np_vals_for_json(row.sum()),
            # Count of Datasets containing this Species
            self._keys[SNKeys.ROW_COUNT]: convert_np_vals_for_json(row.nnz),
            # Return min/max count in this species and datasets for that count
            self._keys[SNKeys.ROW_MIN_COUNT]: minval,
            # self._keys[SNKeys.ROW_MIN_LABELS]: min_row_labels,
            self._keys[SNKeys.ROW_MAX_COUNT]: maxval,
            # self._keys[SNKeys.ROW_MAX_LABELS]: max_row_labels,
        }
        return stats

    # ...............................................
    def compare_column_to_others(self, col_label, agg_type=None):
        """Compare the number of rows and counts in rows to those of other columns.

        Args:
            col_label: label on the column to compare.
            agg_type: return stats on rows or values.  If None, return both.
                (options: "axis", "value", None)

        Returns:
            comparisons (dict): comparison measures
        """
        # Get this column stats
        stats = self.get_column_stats(col_label)
        # Show this column totals and counts compared to min, max, mean of all columns
        all_stats = self.get_all_col_stats()
        comparisons = {self._keys[SNKeys.COL_TYPE]: col_label}
        if agg_type in ("value", None):
            comparisons["Occurrences"] = {
                self._keys[SNKeys.COL_TOTAL]: stats[self._keys[SNKeys.COL_TOTAL]],
                self._keys[SNKeys.COLS_TOTAL]: all_stats[self._keys[SNKeys.COLS_TOTAL]],
                self._keys[SNKeys.COLS_MIN]: all_stats[self._keys[SNKeys.COLS_MIN]],
                self._keys[SNKeys.COLS_MAX]: all_stats[self._keys[SNKeys.COLS_MAX]],
                self._keys[SNKeys.COLS_MEAN]: all_stats[self._keys[SNKeys.COLS_MEAN]],
                self._keys[SNKeys.COLS_MEDIAN]: all_stats[self._keys[SNKeys.COLS_MEDIAN]]
            }
        if agg_type in ("axis", None):
            comparisons["Species"] = {
                self._keys[SNKeys.COL_COUNT]: stats[self._keys[SNKeys.COL_COUNT]],
                self._keys[SNKeys.COLS_COUNT]: all_stats[self._keys[SNKeys.COLS_COUNT]],
                self._keys[SNKeys.COLS_COUNT_MIN]:
                    all_stats[self._keys[SNKeys.COLS_COUNT_MIN]],
                self._keys[SNKeys.COLS_COUNT_MAX]:
                    all_stats[self._keys[SNKeys.COLS_COUNT_MAX]],
                self._keys[SNKeys.COLS_COUNT_MEAN]:
                    all_stats[self._keys[SNKeys.COLS_COUNT_MEAN]],
                self._keys[SNKeys.COLS_COUNT_MEDIAN]:
                    all_stats[self._keys[SNKeys.COLS_COUNT_MEDIAN]]
            }
        return comparisons

    # ...............................................
    def compare_row_to_others(self, row_label, agg_type=None):
        """Compare the number of columns and counts in columns to those of other rows.

        Args:
            row_label: label on the row to compare.
            agg_type: return stats on rows or values.  If None, return both.
                (options: "axis", "value", None)

        Returns:
            comparisons (dict): comparison measures
        """
        stats = self.get_row_stats(row_label)
        # Show this column totals and counts compared to min, max, mean of all columns
        all_stats = self.get_all_row_stats()
        comparisons = {self._keys[SNKeys.ROW_TYPE]: row_label}
        if agg_type in ("value", None):
            comparisons["Occurrences"] = {
                self._keys[SNKeys.ROW_TOTAL]: stats[self._keys[SNKeys.ROW_TOTAL]],
                self._keys[SNKeys.ROWS_TOTAL]: all_stats[self._keys[SNKeys.ROWS_TOTAL]],
                self._keys[SNKeys.ROWS_MIN]: all_stats[self._keys[SNKeys.ROWS_MIN]],
                self._keys[SNKeys.ROWS_MAX]: all_stats[self._keys[SNKeys.ROWS_MAX]],
                self._keys[SNKeys.ROWS_MEAN]: all_stats[self._keys[SNKeys.ROWS_MEAN]],
                self._keys[SNKeys.ROWS_MEDIAN]:
                    all_stats[self._keys[SNKeys.ROWS_MEDIAN]],
            }
        if agg_type in ("axis", None):
            comparisons["Datasets"] = {
                self._keys[SNKeys.ROW_COUNT]: stats[self._keys[SNKeys.ROW_COUNT]],
                self._keys[SNKeys.ROWS_COUNT]: all_stats[self._keys[SNKeys.ROWS_COUNT]],
                self._keys[SNKeys.ROWS_COUNT_MIN]:
                    all_stats[self._keys[SNKeys.ROWS_COUNT_MIN]],
                self._keys[SNKeys.ROWS_COUNT_MAX]:
                    all_stats[self._keys[SNKeys.ROWS_COUNT_MAX]],
                self._keys[SNKeys.ROWS_COUNT_MEAN]:
                    all_stats[self._keys[SNKeys.ROWS_COUNT_MEAN]],
                self._keys[SNKeys.ROWS_COUNT_MEDIAN]:
                    all_stats[self._keys[SNKeys.ROWS_COUNT_MEDIAN]]
            }
        return comparisons

    # ...............................................
    def _upload_to_s3(self, full_filename, bucket, bucket_path, region):
        """Upload a file to S3.

        Args:
            full_filename (str): Full filename to the file to upload.
            bucket (str): Bucket identifier on S3.
            bucket_path (str): Parent folder path to the S3 data.
            region (str): AWS region to upload to.

        Returns:
            s3_filename (str): path including bucket, bucket_folder, and filename for the
                uploaded data
        """
        s3_filename = None
        s3_client = boto3.client("s3", region_name=region)
        obj_name = os.path.basename(full_filename)
        if bucket_path:
            obj_name = f"{bucket_path}/{obj_name}"
        try:
            s3_client.upload_file(full_filename, bucket, obj_name)
        except SSLError:
            self._logme(
                f"Failed with SSLError to upload {obj_name} to {bucket}",
                log_level=ERROR)
        except ClientError as e:
            self._logme(
                f"Failed to upload {obj_name} to {bucket}, ({e})",
                log_level=ERROR)
        else:
            s3_filename = f"s3://{bucket}/{obj_name}"
            self._logme(f"Uploaded {s3_filename} to S3")
        return s3_filename

    # .............................................................................
    def compress_to_file(self, local_path="/tmp"):
        """Compress this SparseMatrix to a zipped npz and json file.

        Args:
            local_path (str): Absolute path of local destination path

        Returns:
            zip_fname (str): Local output zip filename.

        Raises:
            Exception: on failure to write sparse matrix to NPZ file.
            Exception: on failure to serialize metadata as JSON.
            Exception: on failure to write metadata json string to file.
            Exception: on failure to write sparse matrix and category files to zipfile.
        """
        basename = Summaries.get_filename(self._table_type, self._data_datestr)
        mtx_fname = f"{local_path}/{basename}.npz"
        meta_fname = f"{local_path}/{basename}.json"
        zip_fname = f"{local_path}/{basename}.zip"
        # Delete any local temp files
        for fname in [mtx_fname, meta_fname, zip_fname]:
            if os.path.exists(fname):
                self._logme("Removing {fname}", log_level=INFO)
                os.remove(fname)
        # Save matrix to npz locally
        try:
            scipy.sparse.save_npz(mtx_fname, self._coo_array, compressed=True)
        except Exception as e:
            msg = f"Failed to write {mtx_fname}: {e}"
            self._logme(msg, log_level=ERROR)
            raise Exception(msg)
        # Save table data and categories to json locally
        metadata = Summaries.get_table(self._table_type)
        metadata["row"] = self._row_categ.categories.tolist()
        metadata["column"] = self._col_categ.categories.tolist()
        try:
            metastr = json.dumps(metadata)
        except Exception as e:
            msg = f"Failed to serialize metadata as JSON: {e}"
            self._logme(msg, log_level=ERROR)
            raise Exception(msg)
        try:
            with open(meta_fname, 'w') as outf:
                outf.write(metastr)
        except Exception as e:
            msg = f"Failed to write metadata to {meta_fname}: {e}"
            self._logme(msg, log_level=ERROR)
            raise Exception(msg)

        # Compress matrix with categories
        try:
            with ZipFile(zip_fname, 'w') as zip:
                for fname in [mtx_fname, meta_fname]:
                    zip.write(fname, os.path.basename(fname))
        except Exception as e:
            msg = f"Failed to write {zip_fname}: {e}"
            self._logme(msg, log_level=ERROR)
            raise Exception(msg)

        return zip_fname

    # .............................................................................
    @classmethod
    def uncompress_zipped_sparsematrix(
            cls, zip_filename, local_path="/tmp", overwrite=False):
        """Uncompress a zipped SparseMatrix into a coo_array and row/column categories.

        Args:
            zip_filename (str): Filename of output data to write to S3.
            local_path (str): Absolute path of local destination path
            overwrite (bool): Flag indicating whether to use existing files unzipped
                from the zip_filename.

        Returns:
            coo_array (scipy.sparse.coo_array):
            row_categories (pandas.api.types.CategoricalDtype): row categories
            col_categories (pandas.api.types.CategoricalDtype): column categories.

        Raises:
            Exception: on missing input zipfile
            Exception: on missing expected file from zipfile
            Exception: on unable to load NPZ file
            Exception: on unable to load JSON metadata file
            Exception: on missing row categories in JSON
            Exception: on missing column categories in JSON
            Exception: on missing table_type code in JSON
            Exception: on bad table_type code in JSON

        Note:
            All filenames have the same basename with extensions indicating which data
                they contain. The filename contains a string like YYYY-MM-DD which
                indicates which GBIF data dump the statistics were built upon.
        """
        if not os.path.exists(zip_filename):
            raise Exception(f"Missing file {zip_filename}")
        basename = os.path.basename(zip_filename)
        fname, _ext = os.path.splitext(basename)
        try:
            table_type, data_datestr = Summaries.get_tabletype_datestring_from_filename(
                zip_filename)
        except Exception:
            raise
        # Expected files from archive
        mtx_fname = f"{local_path}/{fname}.npz"
        meta_fname = f"{local_path}/{fname}.json"

        # Delete local data files if overwrite
        for fname in [mtx_fname, meta_fname]:
            if os.path.exists(fname) and overwrite is True:
                os.remove(fname)

        # Unzip to local dir
        with ZipFile(zip_filename, mode="r") as archive:
            archive.extractall(f"{local_path}/")
        for fn in [mtx_fname, meta_fname]:
            if not os.path.exists(fn):
                raise Exception(f"Missing expected file {fn}")

        # Save matrix to npz locally
        try:
            sparse_coo = scipy.sparse.load_npz(mtx_fname)
        except Exception as e:
            raise Exception(f"Failed to load {mtx_fname}: {e}")
        # Read JSON dictionary as string
        try:
            with open(meta_fname) as metaf:
                meta_str = metaf.read()
        except Exception as e:
            raise Exception(f"Failed to load {meta_fname}: {e}")
        # Load metadata from string
        try:
            meta_dict = json.loads(meta_str)
        except Exception as e:
            raise Exception(f"Failed to load {meta_fname}: {e}")
        try:
            row_catlst = meta_dict.pop("row")
        except KeyError:
            raise Exception(f"Missing row categories in {meta_fname}")
        else:
            row_categ = CategoricalDtype(row_catlst, ordered=True)
        try:
            col_catlst = meta_dict.pop("column")
        except KeyError:
            raise Exception(f"Missing column categories in {meta_fname}")
        else:
            col_categ = CategoricalDtype(col_catlst, ordered=True)

        return sparse_coo, row_categ, col_categ, table_type, data_datestr

    # .............................................................................
    def write_to_s3(self, bucket, bucket_path, filename, region):
        """Write a pd DataFrame to CSV or parquet on S3.

        Args:
            bucket (str): Bucket identifier on S3.
            bucket_path (str): Folder path to the S3 output data.
            filename (str): Filename of local data to write to S3.
            region (str): AWS region to upload to.

        Returns:
            s3_filename (str): S3 object with bucket and folders.
        """
        s3_fname = self._upload_to_s3(filename, bucket, bucket_path, region)
        return s3_fname

    # .............................................................................
    def copy_logfile_to_s3(self, bucket, bucket_path, region):
        """Write a the logfile to S3.

        Args:
            bucket (str): Bucket identifier on S3.
            bucket_path (str): Folder path to the S3 output data.
            region (str): AWS region to upload to.

        Returns:
            s3_filename (str): S3 object with bucket and folders.

        Raises:
            Exception: if logger is not present.
        """
        if self._logger is None:
            raise Exception("No logfile to write")

        s3_filename = self._upload_to_s3(
            self._logger.filename, bucket, bucket_path, region)
        return s3_filename


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    """Main script creates a SPECIES_DATASET_MATRIX from DATASET_SPECIES_LISTS."""
    data_datestr = get_current_datadate_str()
    # Create a logger
    script_name = os.path.splitext(os.path.basename(__file__))[0]
    todaystr = get_today_str()
    log_name = f"{script_name}_{todaystr}"
    # Create logger with default INFO messages
    tst_logger = Logger(
        log_name, log_path=LOCAL_OUTDIR, log_console=True, log_level=INFO)

    stacked_table_type = SUMMARY_TABLE_TYPES.DATASET_SPECIES_LISTS
    mtx_table_type = SUMMARY_TABLE_TYPES.SPECIES_DATASET_MATRIX

    local_path = "/tmp"

    # Datasets in rows/x/axis 1
    table = Summaries.get_table(stacked_table_type, data_datestr)
    stk_col_label_for_axis1 = table["key_fld"]
    stk_col_label_for_val = table["value_fld"]
    # Dict of new fields constructed from existing fields, just 1 for species key/name
    fld_mods = table["combine_fields"]
    # Species (taxonKey + name) in columns/y/axis 0
    stk_col_label_for_axis0 = list(fld_mods.keys())[0]
    (fld1, fld2) = fld_mods[stk_col_label_for_axis0]
    pqt_fname = f"{table['fname']}.parquet"

    # Read stacked (record) data directly into DataFrame
    stk_df = read_s3_parquet_to_pandas(
        PROJ_BUCKET, SUMMARY_FOLDER, pqt_fname, tst_logger, s3_client=None
    )

    # .................................
    # Combine key and species fields to ensure uniqueness
    def _combine_columns(row):
        return str(row[fld1]) + ' ' + str(row[fld2])
    # ......................
    stk_df[stk_col_label_for_axis0] = stk_df.apply(_combine_columns, axis=1)
    # .................................

    # Create matrix from record data
    agg_sparse_mtx = SparseMatrix.init_from_stacked_data(
        stk_df, stk_col_label_for_axis1, stk_col_label_for_axis0, stk_col_label_for_val,
        mtx_table_type, data_datestr, logger=tst_logger)

    # Test raw counts between stacked data and sparse matrix
    for stk_lbl, axis in ((stk_col_label_for_axis0, 0), (stk_col_label_for_axis1, 1)):
        # Test stacked column used for axis 0/1 against sparse matrix axis 0/1
        test_stacked_to_aggregate_sum(
            stk_df, stk_lbl, stk_col_label_for_val, agg_sparse_mtx, agg_axis=axis,
            test_count=5, logger=tst_logger)

    # Test min/max values for rows/columns
    for is_max in (False, True):
        for axis in (0, 1):
            test_stacked_to_aggregate_extremes(
                stk_df, stk_col_label_for_axis0, stk_col_label_for_axis1,
                stk_col_label_for_val, agg_sparse_mtx, agg_axis=axis, test_count=5,
                logger=tst_logger, is_max=is_max)

    # .................................
    # Save matrix to S3
    out_filename = agg_sparse_mtx.compress_to_file()
    agg_sparse_mtx._upload_to_s3(out_filename, PROJ_BUCKET, SUMMARY_FOLDER, REGION)
    # agg_sparse_mtx.write_to_s3(PROJ_BUCKET, SUMMARY_FOLDER, out_filename, REGION)

    # Copy logfile to S3
    agg_sparse_mtx.write_to_s3(PROJ_BUCKET, SUMMARY_FOLDER, tst_logger.filename, REGION)
    s3_logfile = agg_sparse_mtx.copy_logfile_to_s3(PROJ_BUCKET, SUMMARY_FOLDER, REGION)
    print(s3_logfile)

    # .................................
    table = Summaries.get_table(mtx_table_type, data_datestr)
    zip_fname = f"{table['fname']}.zip"
    # Only download if file does not exist
    zip_filename = download_from_s3(
        PROJ_BUCKET, SUMMARY_FOLDER, zip_fname, local_path=local_path,
        overwrite=False)

    # Only extract if files do not exist
    sparse_coo, row_categ, col_categ, table_type, _data_datestr = \
        SparseMatrix.uncompress_zipped_sparsematrix(
            zip_filename, local_path=local_path, overwrite=False)
    # Create
    sp_mtx = SparseMatrix(
        sparse_coo, mtx_table_type, data_datestr, row_category=row_categ,
        column_category=col_categ, logger=None)

"""
from sppy.aws.aggregate_matrix import *

# Create a logger
script_name = "testing"
todaystr = get_today_str()
log_name = f"{script_name}_{todaystr}"
data_datestr = get_current_datadate_str()

# Create logger with default INFO messages
tst_logger = Logger(
    log_name, log_path=LOCAL_OUTDIR, log_console=True, log_level=INFO)

stacked_table_type = SUMMARY_TABLE_TYPES.DATASET_SPECIES_LISTS
mtx_table_type = SUMMARY_TABLE_TYPES.SPECIES_DATASET_MATRIX

local_path = "/tmp"

# Datasets in rows/x/axis 1
table = Summaries.get_table(stacked_table_type, data_datestr)
stk_col_label_for_axis1 = table["key_fld"]
stk_col_label_for_val = table["value_fld"]
# Dict of new fields constructed from existing fields, just 1 for species key/name
fld_mods = table["combine_fields"]
# Species (taxonKey + name) in columns/y/axis 0
stk_col_label_for_axis0 = list(fld_mods.keys())[0]
(fld1, fld2) = fld_mods[stk_col_label_for_axis0]
pqt_fname = f"{table['fname']}.parquet"

# Read stacked (record) data directly into DataFrame
stk_df = read_s3_parquet_to_pandas(
    PROJ_BUCKET, SUMMARY_FOLDER, pqt_fname, tst_logger, s3_client=None
)

# .................................
# Combine key and species fields to ensure uniqueness
def _combine_columns(row):
    return str(row[fld1]) + ' ' + str(row[fld2])

# ......................
stk_df[stk_col_label_for_axis0] = stk_df.apply(_combine_columns, axis=1)
# .................................

# Create matrix from record data
agg_sparse_mtx = SparseMatrix.init_from_stacked_data(
    stk_df, stk_col_label_for_axis1, stk_col_label_for_axis0, stk_col_label_for_val,
    mtx_table_type, data_datestr, logger=tst_logger)

# Test raw counts between stacked data and sparse matrix
for stk_lbl, axis in ((stk_col_label_for_axis0, 0), (stk_col_label_for_axis1, 1)):
    # Test stacked column used for axis 0/1 against sparse matrix axis 0/1
    test_stacked_to_aggregate_sum(
        stk_df, stk_lbl, stk_col_label_for_val, agg_sparse_mtx, agg_axis=axis,
        test_count=5, logger=tst_logger)

# Test min/max values for rows/columns
for is_max in (False, True):
    for axis in (0, 1):
        test_stacked_to_aggregate_extremes(
            stk_df, stk_col_label_for_axis0, stk_col_label_for_axis1,
            stk_col_label_for_val, agg_sparse_mtx, agg_axis=axis, test_count=5,
            logger=tst_logger, is_max=is_max)

# .................................
# Save matrix to S3
out_filename = agg_sparse_mtx.compress_to_file()
agg_sparse_mtx.write_to_s3(PROJ_BUCKET, SUMMARY_FOLDER, out_filename, REGION)

# Copy logfile to S3
s3_logfile = agg_sparse_mtx.write_to_s3(PROJ_BUCKET, SUMMARY_FOLDER, tst_logger.filename, REGION)
print(s3_logfile)

zip_filename = download_from_s3(
    PROJ_BUCKET, SUMMARY_FOLDER, zip_fname, local_path=local_path,
    overwrite=False)

# .................................
# Read matrix from S3
table = Summaries.get_table(mtx_table_type, data_datestr)
zip_fname = f"{table['fname']}.zip"
# Only download if file does not exist
zip_filename = download_from_s3(
    PROJ_BUCKET, SUMMARY_FOLDER, zip_fname, local_path=local_path,
    overwrite=False)

# Only extract if files do not exist
sparse_coo, row_categ, col_categ, table_type, new_data_datestr = \
    SparseMatrix.uncompress_zipped_sparsematrix(
        zip_filename, local_path=local_path, overwrite=False)

# Create
sp_mtx = SparseMatrix(
    sparse_coo, mtx_table_type, data_datestr, row_category=row_categ,
    column_category=col_categ, logger=tst_logger)

# --------------------------------------------------------------------------------------
# Testing
# --------------------------------------------------------------------------------------

x_vals = get_random_values_from_stacked_data(stk_df, x_col_label, test_count)
y_vals = get_random_values_from_stacked_data(stk_df, y_col_label, test_count)

y_vals = agg_sparse_mtx.get_random_labels(test_count, axis=0)
x_vals = agg_sparse_mtx.get_random_labels(test_count, axis=1)

x = x_vals[0]
y = y_vals[0]
row_label = y
col_label = x
sp_mtx.get_row_stats(y)
sp_mtx.get_column_stats(x)

"""
