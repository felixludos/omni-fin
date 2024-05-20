from pathlib import Path
import omnifig as fig
import json, random
import pandas as pd
from omnibelt import load_yaml, save_yaml, load_json, save_json
import streamlit as st
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, GridUpdateMode
from omnifin.misc import data_root, repo_root, load_db
from omnifin.datacls import Record, Report, Asset, Account, Transaction, Statement, Verification

# if 'sidebar_state' not in st.session_state:
	# st.session_state.sidebar_state = 'expanded'
# st.set_page_config(layout="wide", initial_sidebar_state=st.session_state.sidebar_state)
# import pandas as pd

# df = pd.DataFrame(
#     [
#         {"command": "st.selectbox", "rating": 4, "is_widget": True},
#         {"command": "st.balloons", "rating": 5, "is_widget": False},
#         {"command": "st.time_input", "rating": 3, "is_widget": True},
#     ]
# )
# edited_df = st.data_editor(
#     df,
#     column_config={
#         "command": "Streamlit Command",
#         "rating": st.column_config.NumberColumn(
#             "Your rating",
#             help="How much do you like this command (1-5)?",
#             min_value=1,
#             max_value=5,
#             step=1,
#             format="%d ⭐",
#         ),
#         "is_widget": "Widget ?",
#     },
#     disabled=["command", "is_widget"],
#     hide_index=True,
# )
# favorite_command = edited_df.loc[edited_df["rating"].idxmax()]["command"]
# st.markdown(f"Your favorite command is **{favorite_command}** 🎈")

# st_tags(
#     label='# Enter Keywords:',
#     text='Press enter to add more',
#     value=['Zero', 'One', 'Two'],
#     suggestions=['five', 'six', 'seven',
#                  'eight', 'nine', 'three',
#                  'eleven', 'ten', 'four'],
#     maxtags = 4,
#     key='1')


# gb1 = GridOptionsBuilder.from_dataframe(df)
# gb1.configure_default_column(groupable=True, enableRowGroup=True, aggFunc='sum', filterable=True)
# gb1.configure_selection(selection_mode='multiple', pre_selected_rows=[0])
# # Add checkbox to header to select/deslect all the columns
# gb1.configure_side_bar()
# gridOptions1 = gb1.build()

# Always show in case columns are expanded and then go past width
# gridOptions1['alwaysShowHorizontalScroll'] = True
# gridOptions1['scrollbarWidth'] = 8

# grid_response1 = AgGrid(df,
# 						gridOptions=gridOptions1,
# 						# allow_unsafe_jscode=True,
# 						update_mode=GridUpdateMode.SELECTION_CHANGED,
# 						# enable_enterprise_modules=True,
# 						# custom_css=custom_css,
# 						# columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
# 						height=400)



# import pandas as pd
# import streamlit as st
# import streamlit.components.v1 as components
# from pandas.api.types import (
#     is_categorical_dtype,
#     is_datetime64_any_dtype,
#     is_numeric_dtype,
#     is_object_dtype,
# )
#
#
# def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
#     """
#     Adds a UI on top of a dataframe to let viewers filter columns
#
#     Args:
#         df (pd.DataFrame): Original dataframe
#
#     Returns:
#         pd.DataFrame: Filtered dataframe
#     """
#     modify = st.checkbox("Add filters")
#
#     if not modify:
#         return df
#
#     df = df.copy()
#
#     # Try to convert datetimes into a standard format (datetime, no timezone)
#     for col in df.columns:
#         if is_object_dtype(df[col]):
#             try:
#                 df[col] = pd.to_datetime(df[col])
#             except Exception:
#                 pass
#
#         if is_datetime64_any_dtype(df[col]):
#             df[col] = df[col].dt.tz_localize(None)
#
#     modification_container = st.container()
#
#     with modification_container:
#         to_filter_columns = st.multiselect("Filter dataframe on", df.columns)
#         for column in to_filter_columns:
#             left, right = st.columns((1, 20))
#             # Treat columns with < 10 unique values as categorical
#             if is_categorical_dtype(df[column]) or df[column].nunique() < 10:
#                 user_cat_input = right.multiselect(
#                     f"Values for {column}",
#                     df[column].unique(),
#                     default=list(df[column].unique()),
#                 )
#                 df = df[df[column].isin(user_cat_input)]
#             elif is_numeric_dtype(df[column]):
#                 _min = float(df[column].min())
#                 _max = float(df[column].max())
#                 step = (_max - _min) / 100
#                 user_num_input = right.slider(
#                     f"Values for {column}",
#                     min_value=_min,
#                     max_value=_max,
#                     value=(_min, _max),
#                     step=step,
#                 )
#                 df = df[df[column].between(*user_num_input)]
#             elif is_datetime64_any_dtype(df[column]):
#                 user_date_input = right.date_input(
#                     f"Values for {column}",
#                     value=(
#                         df[column].min(),
#                         df[column].max(),
#                     ),
#                 )
#                 if len(user_date_input) == 2:
#                     user_date_input = tuple(map(pd.to_datetime, user_date_input))
#                     start_date, end_date = user_date_input
#                     df = df.loc[df[column].between(start_date, end_date)]
#             else:
#                 user_text_input = right.text_input(
#                     f"Substring or regex in {column}",
#                 )
#                 if user_text_input:
#                     df = df[df[column].astype(str).str.contains(user_text_input)]
#
#     return df
# data_url = "https://raw.githubusercontent.com/mcnakhaee/palmerpenguins/master/palmerpenguins/data/penguins.csv"
#
# df = pd.read_csv(data_url)
# st.dataframe(filter_dataframe(df))


# from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, GridUpdateMode
#
#
# url = 'https://raw.githubusercontent.com/fivethirtyeight/data/master/airline-safety/airline-safety.csv'
# # url = "https://raw.githubusercontent.com/mcnakhaee/palmerpenguins/master/palmerpenguins/data/penguins.csv"
#
# df = pd.read_csv(url)
#
# # gridOptions = GridOptionsBuilder.from_dataframe(df)
# # gridOptions.configure_column("airline", autoSizeStrategy=400)
#
# AgGrid(df, editable=True, height=800,
# 	   autoSizeStrategy='fit_columns',
# 	   # gridOptions=gridOptions.build(),
# 	   # columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
# )


st.set_page_config(layout="wide")

@st.cache_resource
def load_config():
	fig.initialize()
	return fig.create_config('app')
cfg = load_config()


@st.cache_resource
def load_data():
	root = repo_root()
	conn = load_db(root / 'db' / 'novo.db')
	Record.set_conn(conn)

	year = cfg.pull('year', None)

	full = list(Transaction.find_all())
	if year is not None:
		full = [txn for txn in full if txn.date.year == year]

	items = [{
		'date': txn.date, 'location': txn.location, 'sender': txn.sender.name, 'receiver': txn.receiver.name,
			  'amount': txn.amount, 'unit': txn.unit.name,
			  'received_amount': txn.amount if txn.received_amount is None else txn.received_amount,
			  'received_unit': txn.unit.name if txn.received_amount is None else txn.received_unit.name,
			  'description': txn.description, 'tags': ','.join([tag.name for tag in txn.tags()])
			  } for txn in full]

	df = pd.DataFrame(items, index=[txn.ID for txn in full])
	return df

df = load_data()


# url = 'https://raw.githubusercontent.com/fivethirtyeight/data/master/airline-safety/airline-safety.csv'
# # # url = "https://raw.githubusercontent.com/mcnakhaee/palmerpenguins/master/palmerpenguins/data/penguins.csv"
# #
# df = pd.read_csv(url)


f'{len(df)} rows loading'


st.data_editor(df)


# gridOptions = GridOptionsBuilder.from_dataframe(df)
# gridOptions.configure_column("airline", autoSizeStrategy=400)

# AgGrid(df.head(100),
# 	   editable=True, height=600,
# 	   autoSizeStrategy='fit_columns',
# 	   # gridOptions=gridOptions.build(),
# 	   # columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
# )

'done'

