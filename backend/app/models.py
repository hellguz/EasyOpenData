from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()

class Building(Base):
    __tablename__ = 'building'

    gml_id = Column(String, primary_key=True)
    name = Column(String)
    geom = Column(Geometry('MULTIPOLYGONZ', srid=4326))  # Adjust geometry type as needed

from pydantic import BaseModel

class RegionRequest(BaseModel):
    region: dict  # Adjust the type if you have a more specific structure
