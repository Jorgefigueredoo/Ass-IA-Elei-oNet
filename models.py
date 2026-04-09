from sqlalchemy import Column, Integer, String, Boolean, DateTime
from database import Base
import datetime

class AuditoriaAtendimento(Base):
    __tablename__ = "auditoria_atendimentos"

    id = Column(Integer, primary_key=True, index=True)
    pergunta_eleitor = Column(String, nullable=False)
    resposta_ia = Column(String, nullable=False)
    precisou_encaminhar = Column(Boolean, default=False)
    tema_recorrente = Column(String, nullable=True)
    data_hora = Column(DateTime, default=datetime.datetime.utcnow)