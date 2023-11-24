"""Rental vs. Airbnb listings interactive maps
Author: Christina Cameron
Date: 20/10/2023"""

import warnings
import pandas as pd
import numpy as np
import geopandas as gpd
import topojson as tp
import plotly.express as px

# Related to the NZ.Stat Excel file:
NUM_ROWS_TO_SKIP = 2 # number of rows before header, not including 
                     # "Dataset: ..." cell
HEADER_ROW = 2 # 0-indexed row (not including "Dataset: ..." cell) to use as 
               # column labels
INDEX_COL = 0 # 0-indexed column to use as row labels
FOOTER_LENGTH = 3 # number of rows in footer
CATEGORIES = ["1 bedroom", "2 bedrooms", "3 bedrooms", "4 bedrooms", 
              "5 bedrooms", "6 bedrooms", "7 bedrooms", "8 or more bedrooms", 
              "Total households stated - number of bedrooms"] # categories to 
                                                              # be merged
COLS_PER_CATEGORY = 9 # number of columns that fall into each category

# Related to topology:
NZ_CRS = 2193 # map projection code most commonly used for NZ
TOPOLOGY_CRS = 3857 # map projection code needed when simplifying topology
TOPOLOGY_WEIGHT = 10 # weight for topology simplification
WGS84_CRS = 4326 # map projection code commonly used for online/global data
BUFFER = 0 # buffer between map polygons

# Other:
NA_REPLACEMENT = 0 # replacement value for NA or confidential values
NIGHTS_IN_WEEK = 7 # for converting Airbnb rates from nightly to weekly
BEDROOMS_ORDER = ["1", "2", "3", "4", "5", "6", "7", "8 or more", 
                  "total"] # order of unique bedroom categories


def dotstat_import(filename):
  """Imports and cleans rental listings data from NZ.Stat.
  Returns the Excel file as a dataframe.
  Could be improved to extend functionality to any NZ.Stat data.
  IMPORTANT: Convert .xls files to .xlsx in Excel before using."""
  dataframe = (pd.read_excel(filename, skiprows = NUM_ROWS_TO_SKIP, 
                             header = HEADER_ROW, index_col = INDEX_COL, 
                             skipfooter = FOOTER_LENGTH)
               .drop("Unnamed: 1", axis = 1)
               .drop("Area", axis = 0))
  suffix_num = 0
  col_within_category = 0
  col_num = 0
  while suffix_num < len(CATEGORIES):
    while col_within_category < COLS_PER_CATEGORY:
      for column in dataframe.columns[col_num:col_num + COLS_PER_CATEGORY]:
        new_column_name = column.removesuffix(f".{suffix_num}") 
        new_column_name = f"{CATEGORIES[suffix_num]}: {new_column_name}" 
        dataframe.rename(columns = {column: new_column_name}, inplace = True)
        col_within_category += 1
        col_num += 1
    suffix_num += 1 
    col_within_category = 0
  dataframe.replace(to_replace = "..", value = NA_REPLACEMENT, inplace = True)
  dataframe.index = dataframe.index.map(lambda x: str(x)[2:])
  dataframe = dataframe.iloc[1:, 0:]
  return dataframe


def sa2_import(city_name):
  """Imports SA2 shapefile and filters to desired city.
  Returns a geodataframe for the chosen city ("Auckland", "Wellington City" or 
  "Christchurch City")."""
  filename = (r"zip://input/shapefiles.zip!statistical-area-2-higher-"
              r"geographies-2018-generalised.shp")
  city_filter = f"TA2018_V_1 = '{city_name}'"
  sa2 = (gpd.read_file(filename, where = city_filter)
         .filter(["SA22018__1", "geometry"])
         .set_crs(NZ_CRS).to_crs(TOPOLOGY_CRS))
  with warnings.catch_warnings():
    warnings.simplefilter(action = "ignore", category = RuntimeWarning)
    sa2 = (tp.Topology(sa2, prequantize = False)
           .toposimplify(TOPOLOGY_WEIGHT).to_gdf())
  sa2 = sa2.to_crs(WGS84_CRS)
  sa2["geometry"] = sa2["geometry"].buffer(BUFFER)
  return sa2


def airbnb_import(airbnb_file, city_sa2):
  """Imports and cleans Airbnb listings data from Inside Airbnb.
  Filter using a city's SA2 geodataframe.
  Returns a geodataframe with Airbnb listings from the chosen city."""
  dataframe = pd.read_csv(airbnb_file, usecols = ["latitude", "longitude", 
                                                  "room_type", "price", 
                                                  "bedrooms"])
  dataframe = dataframe[dataframe["room_type"] == "Entire home/apt"]
  dataframe = gpd.GeoDataFrame(dataframe, 
                               geometry = gpd.points_from_xy(dataframe.longitude,
                               dataframe.latitude), crs = WGS84_CRS)
  nan_replacement = {"bedrooms": 1}
  dataframe.fillna(value = nan_replacement, inplace = True)
  filtered_df = city_sa2.sjoin(dataframe, how = "left", predicate = "contains")
  filtered_df["price"] = (filtered_df["price"].str.replace(",", "")
                          .str.replace("$", "")
                          .astype(float).multiply(NIGHTS_IN_WEEK))
  with warnings.catch_warnings():
    warnings.simplefilter(action = "ignore", category = FutureWarning)
    filtered_df.loc[filtered_df["bedrooms"] > 7, "bedrooms"] = "8 or more"
  filtered_df["bedrooms"] = (filtered_df["bedrooms"].astype(str)
                             .str.replace(".0", ""))
  return filtered_df


def rental_count(rental_df):
  """Takes the output from dotstat_import().
  Returns a dataframe with counts of rental properties in each SA2 and bedroom 
  category."""
  rental_count_df = (rental_df.filter(like = ": Total households stated")
                     .reset_index()
                     .melt(id_vars = ["Weekly rent paid"], 
                           var_name = "bedrooms", value_name = "count", 
                           ignore_index = False)
                     .rename(columns = {"Weekly rent paid": "SA22018__1"})
                     .sort_values(by = ["SA22018__1", "bedrooms"]))
  rental_count_df["bedrooms"] = (rental_count_df["bedrooms"].str
                                 .replace(" bedrooms*: Total households stated",
                                          "", regex = True).str
                                 .replace("Total households stated - number of",
                                          "total"))
  rental_count_df.reset_index(inplace = True, drop = True)
  return rental_count_df


def airbnb_count(city_airbnb_df, rental_df):
  """Takes the output from airbnb_import() and dotstat_import.
  Returns a dataframe with counts of Airbnb listings in each SA2 and bedroom 
  number."""
  airbnb_count_df = city_airbnb_df[["SA22018__1", 
                                    "bedrooms"]].groupby(["SA22018__1", 
                                    "bedrooms"], as_index = False).size()
  total_counts = airbnb_count_df.groupby("SA22018__1", 
                                         as_index = False).sum("size")
  total_counts["bedrooms"] = "total"
  airbnb_count_df = pd.concat([airbnb_count_df, total_counts])
  unique_sa2s = rental_df.index.unique()
  unique_bedrooms = BEDROOMS_ORDER
  all_combinations = pd.DataFrame([(sa2, bedroom) for sa2 in unique_sa2s for 
                                   bedroom in unique_bedrooms], 
                                   columns = ["SA22018__1", "bedrooms"])
  airbnb_count_df = (pd.merge(airbnb_count_df, all_combinations, 
                              on = ["SA22018__1", "bedrooms"], 
                              how = "right").fillna(NA_REPLACEMENT)
                     .sort_values(by = ["SA22018__1", "bedrooms"])
                     .reset_index(drop = True))
  return airbnb_count_df


def assign_rental_price(rental_df):
  """Takes the output from dotstat_import().
  Returns a dataframe with the weighted median price category for valid SA2 and 
  bedroom category combinations."""
  rental_price_df = pd.DataFrame({})
  min_col = 0
  max_col = 8
  with warnings.catch_warnings():
    warnings.simplefilter(action = "ignore", category = FutureWarning)
    while max_col <= len(rental_df.filter(like = "$").columns):
      col_subset = rental_df.filter(like = "$").iloc[0:, min_col:max_col]
      for index, row in col_subset.iterrows():
        total_weight = row.sum()
        median_position = total_weight * 0.5
        i = 0
        cumulative_sum = 0
        while cumulative_sum < median_position:
          cumulative_sum += row[i]
          i += 1
        if cumulative_sum != 0:
          new_row = pd.DataFrame({"SA22018__1": [index], 
                                  "bedrooms": col_subset.columns[i - 1],
                                  "price_str": col_subset.columns[i - 1]})
          new_row["bedrooms"] = (new_row["bedrooms"].str
                                 .replace(" bedrooms*: \S.*$", "", regex = True)
                                 .str
                                 .replace("Total households stated - number of",
                                          "total"))
          new_row["price_str"] = (new_row["price_str"].str
                                  .replace("^.*?(?=\$)",  "", regex = True)
                                  .str.replace("^\$100$", "Under $100", 
                                               regex = True))
          rental_price_df = pd.concat([rental_price_df, new_row],
                                      ignore_index = False)
      min_col += 8
      max_col += 8     
  return rental_price_df


def fill_rental_price(rental_df, incomplete_rental_price):
  """Takes the output from dotstat_import() and assign_rental_price().
  Returns a dataframe with the weighted median price category for ALL SA2 and 
  bedroom category combinations."""
  unique_sa2s = rental_df.index.unique()
  unique_bedrooms = incomplete_rental_price["bedrooms"].unique()
  all_combinations = pd.DataFrame([(sa2, bedroom) for sa2 in unique_sa2s for 
                                   bedroom in unique_bedrooms], 
                                   columns = ["SA22018__1", "bedrooms"])
  rental_price_df = (pd.merge(incomplete_rental_price, all_combinations, 
                             on = ["SA22018__1", "bedrooms"], 
                             how = "right").fillna("0")
                     .sort_values(by = ["SA22018__1", "bedrooms"]))
  rental_price_df["price_basic"] = rental_price_df["price_str"]
  rental_price_df["price_average"] = rental_price_df["price_str"]
  basic_price_dict = {"0": 0.0, "Under $100": 1.0, "$100 - $149": 1.5, 
                      "$150 - $199": 2.0, "$200 - $299": 3.0, "$300 - $399": 
                      4.0, "$400 - $499": 5.0, "$500  - $599": 6.0, 
                      "$600 and over": 7.0}
  average_price_dict = {"0": 0.0, "Under $100": 49.5, "$100 - $149": 124.5, 
                        "$150 - $199": 174.5, "$200 - $299": 249.5, 
                        "$300 - $399": 349.5, "$400 - $499": 449.5, 
                        "$500  - $599": 549.5, "$600 and over": 800.0}
  rental_price_df.price_basic.replace(basic_price_dict, inplace = True)
  rental_price_df.price_average.replace(average_price_dict, inplace = True)
  rental_price_df.reset_index(inplace = True, drop = True)
  return rental_price_df


def airbnb_price(city_airbnb_df, rental_df):
  """Takes the output from airbnb_import() and dotstat_import().
  Returns a dataframe with the median price for each SA2 and bedroom number."""
  airbnb_price_df = (city_airbnb_df[["SA22018__1", "bedrooms", "price"]]
                     .groupby(["SA22018__1", "bedrooms"], as_index = False)
                     .median("price"))
  total_median = (city_airbnb_df[["SA22018__1", "bedrooms", "price"]]
                  .groupby("SA22018__1", as_index = False).median("price"))
  total_median["bedrooms"] = "total"
  airbnb_price_df = pd.concat([airbnb_price_df, total_median])
  unique_sa2s = rental_df.index.unique()
  unique_bedrooms = BEDROOMS_ORDER
  all_combinations = pd.DataFrame([(sa2, bedroom) for sa2 in unique_sa2s for 
                                   bedroom in unique_bedrooms],
                                   columns = ["SA22018__1", "bedrooms"])
  airbnb_price_df = (pd.merge(airbnb_price_df, all_combinations,
                             on = ["SA22018__1", "bedrooms"], 
                             how = "right").fillna(NA_REPLACEMENT)
                     .sort_values(by = ["SA22018__1", "bedrooms"])
                     .reset_index(drop = True))
  return airbnb_price_df


def df_aggregate(city_rental_count, city_airbnb_count, city_rental_price, 
                 city_airbnb_price):
  """Takes the output from (in order) rental_count(), airbnb_count(), 
  fill_rental_price() and airbnb_price().
  Returns one dataframe with just the important columns."""
  aggregate_df = (city_rental_count.join(city_airbnb_count["size"])
                  .join(city_rental_price[["price_str", "price_basic", 
                                           "price_average"]])
                  .join(city_airbnb_price["price"])
                  .rename(columns = {"SA22018__1": "SA2", "bedrooms": 
                          "Bedrooms", "count": "rental_count", "size": 
                          "Airbnb_count", "price_str": "rental_price", 
                          "price_basic": "rental_price_basic", 
                          "price_average": "rental_price_average",
                          "price": "Airbnb_price"}))
  return aggregate_df


def add_ratios(aggregate_df, city_sa2):
  """Takes the output from df_aggregate() and sa2_import().
  Adds a geometry column and ratio columns for count and price."""
  for index, row in aggregate_df.iterrows():
    if row["Airbnb_count"] == row["rental_count"]:
      aggregate_df.loc[index, "count_ratio"] = 0.0
    elif row["Airbnb_count"] > row["rental_count"]:
      if row["rental_count"] == 0:
        aggregate_df.loc[index, "count_ratio"] = row["Airbnb_count"] * (-1 / 
                                                 (row["rental_count"] + 1))
      else:
        aggregate_df.loc[index, "count_ratio"] = row["Airbnb_count"] * (-1 / 
                                                 row["rental_count"])
    else:
      if row["Airbnb_count"] == 0:
        aggregate_df.loc[index, "count_ratio"] = row["rental_count"] * (1 / 
                                                 (row["Airbnb_count"] + 1))
      else:
        aggregate_df.loc[index, "count_ratio"] = row["rental_count"] * (1 / 
                                                 row["Airbnb_count"])
    if row["Airbnb_price"] == row["rental_price_average"]:
      aggregate_df.loc[index, "price_ratio"] = 0.0
    elif row["Airbnb_price"] > row["rental_price_average"]:
      if row["rental_price_average"] == 0:
        aggregate_df.loc[index, "price_ratio"] = row["Airbnb_price"] * (-1 / 
                                                 (row["rental_price_average"] + 
                                                 1))
      else:
        aggregate_df.loc[index, "price_ratio"] = row["Airbnb_price"] * (-1 / 
                                                 row["rental_price_average"])
    else:
      if row["Airbnb_price"] == 0.0:
        aggregate_df.loc[index, "price_ratio"] = (row["rental_price_average"] * 
                                                 (1 / (row["Airbnb_price"] + 
                                                 1)))
      else:
        aggregate_df.loc[index, "price_ratio"] = (row["rental_price_average"] * 
                                                 (1 / row["Airbnb_price"]))
  aggregate_df = city_sa2.merge(aggregate_df, left_on = ["SA22018__1"], 
                                right_on = ["SA2"]).set_index("SA2")
  return aggregate_df


def count_map(aggregate_df, filename, map_type):
  """Takes the output from add_ratios().
  Makes a map displaying the number of either rental properties (map_type = 
  "rental") or Airbnb listings (map_type = "Airbnb") by SA2 and number 
  of bedrooms, and writes it to an HTML file with the given filename."""
  map_object = (px.choropleth(aggregate_df, geojson = aggregate_df.geometry,
                              locations = aggregate_df.index,
                              color = f"{map_type}_count",
                              hover_data = {"Bedrooms": False},
                              projection = "transverse mercator",
                              animation_frame = "Bedrooms",
                              title = fr"Number of {map_type}s, by SA2 and "
                              fr"number of bedrooms", 
                              labels = {f"{map_type}_count": "Count"},
                              category_orders = {"Bedrooms": BEDROOMS_ORDER})
                .update_geos(fitbounds = "locations", visible = False)
                .write_html(f"output/{filename}.html"))
  del map_object


def price_map(aggregate_df, filename, map_type):
  """Takes the output from add_ratios().
  Makes a map displaying the median price of either rental properties (map_type 
  = "rental") or Airbnb listings (map_type = "Airbnb") by SA2 and number 
  of bedrooms, and writes it to an HTML file with the given filename."""
  if map_type == "rental":
    color = "rental_price_basic"
    color_continuous_scale = [[0.0, "gray"], [0.01, "gray"], [0.01, "blue"], 
                              [1.0, "red"]]
    hover_data = {"rental_price": True, "rental_price_basic": False,
                  "Bedrooms": False}
    labels = {"rental_price": "Median price", 
              "rental_price_basic": "Median price (per week)"}
    colorbar_tickprefix = ""
    colorbar_labelalias = {0: "NA", 1: "Under $100", 2: "$100 - $199", 
                           3: "$200 - $299", 4: "$300 - $399", 5: "$400 - $499", 
                           6: "$500 - $599", 7: "$600 and over"}
  else:
    color = "Airbnb_price"
    color_continuous_scale = [[0.0, "gray"], [0.01, "gray"], [0.01, "#30123b"],  
                              [0.07, "#4145ab"], [0.14, "#4675ed"], [0.21, 
                              "#39a2fc"],  [0.28, "#1bcfd4"], [0.35, "#24eca6"], 
                              [0.42, "#61fc6c"], [0.49, "#a4fc3b"], [0.56, 
                              "#d1e834"], [0.63, "#f3c63a"],  [0.70, "#fe9b2d"], 
                              [0.77, "#f36315"], [0.84, "#d93806"], [0.91, 
                              "#b11901"], [1.0, "#7a0402"]]
    hover_data = {"Bedrooms": False, "Airbnb_price": ":$.2f"}
    labels = {"Airbnb_price": "Median price (per week)"}
    colorbar_tickprefix = "$"
    colorbar_labelalias = {"$0": "NA"}
  map_object = (px.choropleth(aggregate_df, geojson = aggregate_df.geometry,
                              locations = aggregate_df.index, color = color,
                              color_continuous_scale = color_continuous_scale,
                              hover_data = hover_data,
                              projection = "transverse mercator",
                              animation_frame = "Bedrooms",
                              title = fr"Median price of {map_type}s, by SA2 "
                              fr"and number of bedrooms",
                              labels = labels,
                              category_orders = {"Bedrooms": BEDROOMS_ORDER})
                .update_geos(fitbounds = "locations", visible = False)
                .update_coloraxes(colorbar_tickprefix = colorbar_tickprefix,
                                  colorbar_labelalias = colorbar_labelalias)
                .write_html(f"output/{filename}.html"))
  del map_object


def ratio_map(aggregate_df, filename, map_type):
  """Takes the output from add_ratios(). 
  Makes a map displaying the ratio of either counts (map_type = "count") or 
  prices (map_type = "price") by SA2 and number of bedrooms, and writes it to 
  an HTML file with the given filename."""
  if map_type == "count":
    hover_data = {"Bedrooms": False, f"rental_{map_type}": True, 
                  f"Airbnb_{map_type}": True, f"{map_type}_ratio": ":.2f"}
    title = (fr"Ratio of rental {map_type}s to Airbnb {map_type}s, by SA2 and "
             fr"number of bedrooms")
  else:
    hover_data = {"Bedrooms": False, f"rental_{map_type}": True, 
                  f"Airbnb_{map_type}": ":$.2f", f"{map_type}_ratio": ":.2f"}
    title = (fr"Ratio of median rental {map_type}s to median Airbnb"
             fr" {map_type}s, by SA2 and number of bedrooms")
  map_object = (px.choropleth(aggregate_df, geojson = aggregate_df.geometry,
                              locations = aggregate_df.index,
                              color = f"{map_type}_ratio",
                              color_continuous_scale = [[0.0, "#7c1d6f"], [0.25, 
                              "#e34f6f"], [0.4999, "#ffe9a3"], [0.4999, 
                              "#ffffff"], [0.5001, "#ffffff"], [0.5001, 
                              "#f7feae"], [0.75, "#46aea0"], [1.0, "#045275"]],
                              hover_data = hover_data,
                              projection = "transverse mercator",
                              animation_frame = "Bedrooms", title = title,
                              labels = {f"{map_type}_ratio": "Ratio", 
                              f"rental_{map_type}": f"Rental {map_type}", 
                              f"Airbnb_{map_type}": f"Airbnb {map_type}"},
                              category_orders = {"Bedrooms": BEDROOMS_ORDER})
                .update_geos(fitbounds = "locations", visible = False)
                .update_coloraxes(cmid = 0.0)
                .write_html(f"output/{filename}.html"))
  del map_object


def main():
  """Imports the files and creates dataframes/geodataframes for the selected
  city, then creates a map of each type for that city and writes them to HTML
  files with the specified prefix."""
  filename = input("Enter the relative path of your Excel file: ")
  rental_df = dotstat_import(filename)
  city = input(r"Choose a city - Auckland, Wellington City, or Christchurch "
               r"City: ")
  city_sa2 = sa2_import(city)
  airbnb_file = input("Enter the relative path of your Airbnb data: ")
  prefix = input("Enter a prefix to add to the map filenames: ")
  city_airbnb_df = airbnb_import(airbnb_file, city_sa2)
  city_rental_count = rental_count(rental_df)
  city_airbnb_count = airbnb_count(city_airbnb_df, rental_df)
  city_rental_price = fill_rental_price(rental_df, 
                                        assign_rental_price(rental_df))
  city_airbnb_price = airbnb_price(city_airbnb_df, rental_df)
  city_agg_df = add_ratios(df_aggregate(city_rental_count, city_airbnb_count, 
                           city_rental_price, city_airbnb_price), city_sa2)
  count_map(city_agg_df, f"{prefix}_rental_count_map", "rental")
  print("1/6 maps done...")
  count_map(city_agg_df, f"{prefix}_airbnb_count_map", "Airbnb")
  print("2/6 maps done...")
  price_map(city_agg_df, f"{prefix}_rental_price_map", "rental")
  print("3/6 maps done...")
  price_map(city_agg_df, f"{prefix}_airbnb_price_map", "Airbnb")
  print("4/6 maps done...")
  ratio_map(city_agg_df, f"{prefix}_count_ratio_map", "count")
  print("5/6 maps done...")
  ratio_map(city_agg_df, f"{prefix}_price_ratio_map", "price")
  print("All done!")

main()
