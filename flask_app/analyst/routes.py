"""URL Routes for the Specify Network API services."""
from flask import Blueprint, Flask, render_template, request

from flask_app.analyst.count import CountSvc
from flask_app.common.constants import (STATIC_DIR, TEMPLATE_DIR)

analyst_blueprint = Blueprint(
    "analyst", __name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR,
    static_url_path="/static")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.register_blueprint(analyst_blueprint)


# .....................................................................................
@app.route('/')
def index():
    return render_template("analyst.index.html")

# # .....................................................................................
# @app.route("/api/v1/", methods=["GET"])
# def analyst_status():
#     """Get services available from broker.
#
#     Returns:
#         dict: A dictionary of status information for the server.
#     """
#     endpoints = APIEndpoint.get_analyst_endpoints()
#     system_status = "In Development"
#     return {
#         "num_services": len(endpoints),
#         "endpoints": endpoints,
#         "status": system_status
#     }
#

# # ..........................
# @app.route("/api/v1/schema")
# def display_raw_schema():
#     """Show the schema XML.
#
#     Returns:
#         schema: the schema for the Specify Network.
#     """
#     fname = os.path.join(SCHEMA_DIR, SCHEMA_FNAME)
#     with open(fname, "r") as f:
#         schema = f.read()
#     return schema
#
#
# # ..........................
# @app.route("/api/v1/swaggerui")
# def swagger_ui():
#     """Show the swagger UI to the schema.
#
#     Returns:
#         a webpage UI of the Specify Network schema.
#     """
#     return render_template("swagger_ui.html")


# .....................................................................................
@app.route("/api/v1/count/")
def count_endpoint():
    """Get the available counts.

    Returns:
        response: A flask_app.analyst API response object containing the count
            API response.
    """
    coll_arg = request.args.get("collection_id", default=None, type=str)
    org_arg = request.args.get("organization_id", default=None, type=str)
    if coll_arg is None and org_arg is None:
        response = CountSvc.get_endpoint()
    else:
        response = CountSvc.get_counts(coll_arg, org_arg)
    return response


# # .....................................................................................
# @app.route("/api/v1/collection/<string:collection_id>", methods=["GET"])
# def collection_get():
#     """Get the available counts.
#
#     Returns:
#         response: A flask_app.analyst API response object containing the count
#             API response for the given collection.
#     """
#     compare_coll_arg = request.args.get("compare_coll_id", default=None, type=str)
#     compare_others_arg = request.args.get("compare_others", default=False, type=bool)
#     compare_total_arg = request.args.get("compare_total", default=False, type=bool)
#     response = CountSvc.get_endpoint(compare_coll_arg, compare_others_arg, compare_total_arg)
#     return response
#
# # .....................................................................................
# @app.route("/api/v1/organization/<string:organization_id>", methods=["GET"])
# def organization_get():
#     """Get the available counts.
#
#     Returns:
#         response: A flask_app.analyst API response object containing the count
#             API response for the given organization.
#     """
#     compare_org_arg = request.args.get("compare_org_id", default=None, type=str)
#     compare_others_arg = request.args.get("compare_others", default=False, type=bool)
#     compare_total_arg = request.args.get("compare_total", default=False, type=bool)
#     response = CountSvc.get_endpoint(
#         compare_org_arg, compare_others_arg, compare_total_arg)
#     return response

# .....................................................................................
# .....................................................................................
if __name__ == "__main__":
    app.run(debug=True)
