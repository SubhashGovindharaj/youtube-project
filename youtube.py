

import statistics

from urllib.error import HTTPError
import pandas as pd
from googleapiclient.discovery import build
import pymongo
import time
import psycopg2
import streamlit as st
import isodate
import re

api_key = "AIzaSyCQodNvJEFKz4NPLB1VtFa6GYWEqpFRPlc"
api_service_name = "youtube"
api_version = "v3"

youtube = build(api_service_name, api_version, developerKey=api_key)

def duration(data):
    dur = isodate.parse_duration(data)
    sec = dur.total_seconds()
    hours = float(int(sec) / 3600)
    return(hours)

def get_channel_details(channel_id):
    request = youtube.channels().list(part = 'snippet,contentDetails,statistics,status',id = channel_id)
    response = request.execute()
    for item in response["items"]:
            data = {
                    'channel_id':str(item["id"]),
                    'channel_name':str(item["snippet"]["title"]),
                    'channel_launch_date':item["snippet"]["publishedAt"],
                    'channel_description':item["snippet"]["description"],
                    'channel_views':int(item["statistics"]["viewCount"]),
                    'channel_subscription':int(item["statistics"]["subscriberCount"]),
                    'channel_video_count':int(item["statistics"]["videoCount"]),
                    'channel_playlist_id':item["contentDetails"]["relatedPlaylists"]["uploads"]
                    }    
    return(data)

def get_playlist_details(playlist):
  video_id = []
  next_page_token = None
  while True:
      request = youtube.playlistItems().list(part = 'contentDetails', playlistId = playlist,  maxResults = 50, pageToken = next_page_token)
      response = request.execute()
      for item in response["items"]:
          video_id.append(item["contentDetails"]["videoId"])
      next_page_token = response.get("nextPageToken")
      if not next_page_token:
        break
  return video_id

def get_video_details(video_ids):
  video_details =[]
  for video_id in video_ids:
    request = youtube.videos().list(part = 'snippet,contentDetails,statistics', id = video_id)
    response = request.execute()
    for item in response["items"]:
        data = {
              'video_id' : item["id"],
              'channel_id' : item["snippet"]["channelId"],
              'channel_name' : item["snippet"]["channelTitle"],
              'video_name' : item["snippet"]["title"],
              'video_date' : item["snippet"]["publishedAt"],
              'video_description' : item["snippet"]["description"],
              'video_duration' :duration(item["contentDetails"]["duration"]),
              'video_views' : int(item["statistics"]["viewCount"])if 'viewCount' in response['items'][0]['statistics'] else 0,
              'video_likes' : int(item["statistics"]["likeCount"]) if 'likeCount' in response['items'][0]['statistics'] else 0,
              'video_dislikes' :int( item["statistics"]["dislikeCount"]) if 'dislikeCount' in response['items'][0]['statistics'] else 0,
              'video_favourite' : int(item["statistics"]["favoriteCount"]) if 'favoriteCount' in response['items'][0]['statistics'] else 0,
              'video_comment_count' : int(item["statistics"]["commentCount"]) if 'commentCount' in response['items'][0]['statistics'] else 0,
              }
        video_details.append(data)
  return video_details

def get_comment_details(video_ids):
    comment_list = []
    for video_id in video_ids:
        try:
            request = youtube.commentThreads().list(part='snippet', videoId=video_id, maxResults=50)
            response = request.execute()          
            if 'items' not in response:
                continue
            for item in response["items"]:
                 comment_details = {
                        'comment_id': item['snippet']['topLevelComment']['id'],
                        'video_id': video_id,
                        'comment_text': item['snippet']['topLevelComment']['snippet']['textDisplay'],
                        'comment_author': item['snippet']['topLevelComment']['snippet']['authorDisplayName'],
                        'commented_on': item['snippet']['topLevelComment']['snippet']['publishedAt']
                        }
                 comment_list.append(comment_details)
        except :
            continue
    return comment_list

def data_to_mongo(input):
    client = pymongo.MongoClient("mongodb+srv://subhashsubhi3112:Subhash@cluster0.dxfvyo6.mongodb.net/?retryWrites=true&w=majority")
    db = client["Youtube"]
    col1 = db["channel_details"]
    existing_channel= col1.find_one({"_id":input})
    if existing_channel is None:
        try:  
            channel = get_channel_details(input)
            playlist_id = channel['channel_playlist_id']
            video = get_playlist_details(playlist_id)
            comment_details = get_comment_details(video)
            video_details = get_video_details(video)
            DATA = {"_id":input,
                    "channel":channel,
                    "video_details":video_details,
                    "comment_details":comment_details}
            col1.insert_one(DATA)
            with st.spinner('Wait for it...'):
                time.sleep(5)
            st.success('Data retrived and loaded into MongoDb..')
        except Exception as e:
            error_message = str(e)
            if "quota" in error_message.lower():
                st.error("Maximum Quota for the day is breached. Please try again after 24 hours.")
            else:
                st.error("An error occurred: " + error_message)
    else:
        st.error("Data Already Exists")

def retrive(data):

    client = pymongo.MongoClient("mongodb+srv://subhashsubhi3112:Subhash@cluster0.dxfvyo6.mongodb.net/?retryWrites=true&w=majority")
    
    db = psycopg2.connect(host='localhost', user='postgres', password='subhash', port=5433, database='youtube_dh')
    exe = db.cursor()

    exe.execute("""create table if not exists channel(
    channel_id varchar unique,
    channel_name text,
    channel_launch_date varchar,
    channel_description text,
    channel_views int,
    channel_subscription int,
    channel_video_count int,
    channel_playlist_id varchar)""")
    db.commit()

    exe.execute("""create table if not exists video (
    video_id varchar unique,
    channel_id varchar,
    channel_name text,
    video_name text,
    video_date varchar,
    video_description text,
    video_duration float,
    video_views int,
    video_likes int,
    video_dislikes int,
    video_favourite int,
    video_comment_count int)""")
    db.commit()

    exe.execute("""create table if not exists comment (
    comment_id varchar unique,
    video_id varchar,
    comment_text text,
    author text,
    comment_date varchar)""")
    db.commit()
    
    channel_data = client["Youtube"]["channel_details"].find_one({'channel.channel_name': data}, {"_id": 0})

    try:
        exe.execute("insert into channel values(%s,%s,%s,%s,%s,%s,%s,%s)",
                            (channel_data['channel']['channel_id'],channel_data['channel']['channel_name'], channel_data['channel']['channel_launch_date'],
                             channel_data['channel']['channel_description'], channel_data['channel']['channel_views'], channel_data['channel']['channel_subscription'],
                             channel_data['channel']['channel_video_count'], channel_data['channel']['channel_playlist_id']))
        db.commit()
        for v in channel_data['video_details']:
            exe.execute("insert into video values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (v['video_id'], v['channel_id'],
                            v['channel_name'], v['video_name'],
                            v['video_date'], v['video_description'],
                            v['video_duration'], v['video_views'],
                            v['video_likes'], v['video_dislikes'],
                            v['video_favourite'], v['video_comment_count']))
            db.commit()
        for v in channel_data['comment_details']:
            exe.execute("insert into comment values(%s,%s,%s,%s,%s)",
                        (v['comment_id'], v['video_id'],
                            v['comment_text'], v['comment_author'],
                            v['commented_on']))
            db.commit()
        st.success("Data Successfully migrated to SQL database.")
    except:
        st.error("you are trying to add duplicates \nData migration done")

def dropdownlist():
     chanelname =[]
     client = pymongo.MongoClient("mongodb+srv://subhashsubhi3112:Subhash@cluster0.dxfvyo6.mongodb.net/?retryWrites=true&w=majority")
     for i in client["Youtube"]["channel_details"].find():
         chanelname.append(i["channel"]["channel_name"])
     return(chanelname)

def analysis(data):
    if data == "Visualisation of video names along with their channel name":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name ,video_name from video")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name",2:"Video Name"}))
        except:
            st.text("Error executing SQL query")

    if data == "Visualisation of channels that have most number of videos along with their video count":
        try:
            db = psycopg2.connect(host='localhost', user='postgres', password='subhash', port=5433, database='youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name ,channel_video_count from channel order by channel_video_count desc limit 5 ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name", 2:"Total Number of Videos"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of top 10 most viewed videos and their respective channels":
        try:
            db = psycopg2.connect(host='localhost', user='postgres', password='subhash', port=5433, database='youtube_dh')
            exe = db.cursor()
            exe.execute("select video_name ,video_views from video order by video_views desc limit 10 ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Video Name", 2:"Total Views"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of no of comments made on each video along with their corresponding video names":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name ,video_name , video_comment_count from video order by channel_name, video_name ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name",2: "Video Name", 3:"Video Comment Count"}))
        except:
            st.text("Error executing SQL query")
        
    if data == "Visualisation of videos that have the highest number of likes along their corresponding channel name.":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'Youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name, video_name ,video_likes from video order by video_likes desc limit 15 ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name",2:"Video Name",3:"Video Likes Count"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of total number of likes and dislikes for each video along with their corresponding video names":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select video_name,video_likes,video_dislikes from video")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Video Name", 2:"Video Likes", 3:"Video Dislikes"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of total number of views for each channel along with their corresponding channel names":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name ,channel_views from channel order by channel_name")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name", 2:"Channel Views"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of names of all the channels that have published videos in the year 2022":
        try: 
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select distinct channel_name from video where video_date like '2022%' ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name"}))
        except:
            st.text("Error executing SQL query")
        
    
    if data == "Visualisation of Average duration of all videos in each channel along with their corresponding channel name.":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name , avg(video_duration) from video group by channel_name")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name", 2:"Average Video Duration in hours"}))
        except:
            st.text("Error executing SQL query")
    
    if data == "Visualisation of Videos that have highest number of comments and their corresponding channel name.":
        try:
            db = psycopg2.connect(host = 'localhost',user = 'postgres',password='subhash',port = 5433,database = 'youtube_dh')
            exe = db.cursor()
            exe.execute("select channel_name,video_name,video_comment_count from video order by video_comment_count desc limit 10 ")
            result = exe.fetchall()
            res = []
            for i in result:
                res.append(i)
            st.dataframe(res,width= 5000,column_config=({1:"Channel Name", 2:"Video Name", 3:"Comment Count"}))
        except:
            st.text("Error executing SQL query")

st.set_page_config(page_title="Youtube Data Harvesting and Warehousing",page_icon="▶️",layout="wide")
st.header(':rainbow[Youtube Data Harvesting and Warehousing]')
st.text("""
""")
col1, col2 =  st.columns(2)
with col1:
    st.markdown(":rainbow[Data Collection Zone]")
    st.caption(":gray[The function block of the zone is to fetch the data from youtube API and to upload the data into MongoDb Database]")
    channel_id = st.text_input(":gray[Enter the Channel ID]")
    submit_1 = st.button("Fetch Data and upload",disabled=False)
    if submit_1:
       data_to_mongo(channel_id)

with col2:
    st.markdown(":rainbow[Data Migration Zone]")
    st.caption(":gray[The function block of the zone is to retrieve the data from the MongoDb database and migrate it to SQL Database]")
    channel_name = st.selectbox('Select the requisite for data migration',options = dropdownlist())
    submit_2 = st.button("Migrate data to SQL",disabled=False)
    if submit_2:
        retrive(channel_name)

Questions = [
        "Visualisation of video names along with their channel name",
        "Visualisation of channels that have most number of videos along with their video count",
        "Visualisation of top 10 most viewed videos and their respective channels",
        "Visualisation of no of comments made on each video along with their corresponding video names",
        "Visualisation of videos that have the highest number of likes along their corresponding channel name.",
        "Visualisation of total number of likes and dislikes for each video along with their corresponding video names",
        "Visualisation of total number of views for each channel along with their corresponding channel names",
        "Visualisation of names of all the channels that have published videos in the year 2022",
        "Visualisation of Average duration of all videos in each channel along with their corresponding channel name.",
        "Visualisation of Videos that have highest number of comments and their corresponding channel name."]

st.markdown(":rainbow[Data Analysis Zone]")
st.caption(":gray[The function block of the zone is to Analyse and visualise the Data Extracted]")
channel_name = st.selectbox('Select the requisite for Analysis',Questions)
submit_3 = st.button("Execute Visualisation",disabled=False)
if submit_3:
    analysis(channel_name)