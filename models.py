from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime

class SessaoAtendimento(Base):
    __tablename__ = "sessoes_atendimento"

    id = Column(Integer, primary_key=True, index=True)
    cpf_eleitor = Column(String, nullable=False, index=True)
    iniciada_em = Column(DateTime, default=datetime.datetime.utcnow)
    ultimo_acesso = Column(DateTime, default=datetime.datetime.utcnow)
    encerrada = Column(Boolean, default=False)

    # Relacionamento com os atendimentos da sessão
    atendimentos = relationship("AuditoriaAtendimento", back_populates="sessao")


class AuditoriaAtendimento(Base):
    __tablename__ = "auditoria_atendimentos"

    id = Column(Integer, primary_key=True, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes_atendimento.id"), nullable=True)
    pergunta_eleitor = Column(String, nullable=False)
    resposta_ia = Column(String, nullable=False)
    precisou_encaminhar = Column(Boolean, default=False)
    tema_recorrente = Column(String, nullable=True)
    data_hora = Column(DateTime, default=datetime.datetime.utcnow)
    tempo_resposta_ms = Column(Float, nullable=True)

    sessao = relationship("SessaoAtendimento", back_populates="atendimentos")