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

    # RELACIONAMENTOS
    sessao = relationship("SessaoAtendimento", back_populates="atendimentos")
    # ESSA LINHA ABAIXO É A QUE ESTÁ DANDO O ERRO. Verifique se ela existe:
    avaliacao = relationship("AvaliacaoAtendimento", back_populates="atendimento", uselist=False)


class AvaliacaoAtendimento(Base):
    __tablename__ = "avaliacoes_atendimento"

    id = Column(Integer, primary_key=True, index=True)
    atendimento_id = Column(Integer, ForeignKey("auditoria_atendimentos.id"), nullable=False)
    util = Column(Boolean, nullable=False)
    comentario = Column(String, nullable=True)

    atendimento = relationship("AuditoriaAtendimento", back_populates="avaliacao")