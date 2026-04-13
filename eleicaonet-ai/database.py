from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Cria um arquivo local chamado eleicaonet.db para armazenar os dados do banco de dados SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./eleicaonet.db"

# connect_args={"check_same_thread": False} é necessário apenas para o SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()