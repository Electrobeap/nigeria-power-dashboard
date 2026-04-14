from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from scraper import fetch_grid_data

app = FastAPI()

@app.get("/")
def home():
	return{"message": "Nigeria Power API running"}

@app.get("/data")
def get_data():
	return fetch_grid_data()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"], 
	allow_credentials=False,	
	allow_methods=["*"],													allow_headers=["*"],
)	
	