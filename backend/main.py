from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from backend.scraper import fetch_grid_data

app = FastAPI()

@app.get("/")
def serve_frontend():	
	return FileResponse("frontend/index.html")

@app.get("/data")
def get_data():
	return fetch_grid_data()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"], 
	allow_credentials=False,	
	allow_methods=["*"],													
	allow_headers=["*"],
)	

import uvicorn 

if __name__ == "__main__":
	uvicorn.run("backend.main:app", host="0.0.0.0", port=10000)
