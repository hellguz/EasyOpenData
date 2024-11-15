from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()

class Building(Base):
    __tablename__ = 'building'

    ogc_fid = Column(Integer, primary_key=True)
    name = Column(String)
    geometry = Column(Geometry('MULTIPOLYGONZ', srid=4326))  # Adjust geometry type as needed
