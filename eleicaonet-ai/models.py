from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    login = Column(String, unique=True, nullable=False)
    senha = Column(String, nullable=False)
    cpf = Column(String, unique=True, nullable=False)

    # Relação: Um utilizador pode ter VÁRIOS votos (um para cada pleito)
    votos = relationship("Voto", back_populates="eleitor")
class Chapa(Base):
    __tablename__ = "chapas"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String, unique=True, nullable=False) # Ex: "C1"
    nome = Column(String, nullable=False) # Ex: "INOVAÇÃO E GESTÃO"

    # Relação: Uma chapa pode receber vários votos
    votos_recebidos = relationship("Voto", back_populates="chapa")

class Voto(Base):
    __tablename__ = "votos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    chapa_id = Column(Integer, ForeignKey("chapas.id"), nullable=True) # Nulo se for Branco/Nulo
    pleito_id = Column(Integer, nullable=False) # NOVA COLUNA: Indica se é Prefeito, Vereador, etc.
    tipo_voto = Column(String, nullable=False) # "VALIDO", "BRANCO", "NULO"
    data_voto = Column(DateTime, default=datetime.datetime.utcnow)

    # Relações
    eleitor = relationship("Usuario", back_populates="votos") # Ajustado para 'votos'
    chapa = relationship("Chapa", back_populates="votos_recebidos")

class SessaoAtendimento(Base):
    __tablename__ = "sessoes_atendimento"

    id = Column(Integer, primary_key=True, index=True)
    cpf_eleitor = Column(String, nullable=False)
    iniciada_em = Column(DateTime, default=datetime.datetime.utcnow)
    ultimo_acesso = Column(DateTime, default=datetime.datetime.utcnow)
    encerrada = Column(Boolean, default=False)

    atendimentos = relationship(
        "AuditoriaAtendimento",
        back_populates="sessao"
    )

class AuditoriaAtendimento(Base):
    __tablename__ = "auditoria_atendimentos"

    id = Column(Integer, primary_key=True, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes_atendimento.id"))

    pergunta_eleitor = Column(String, nullable=False)
    resposta_ia = Column(String, nullable=False)

    precisou_encaminhar = Column(Boolean, default=False)
    tema_recorrente = Column(String, nullable=True)

    data_hora = Column(DateTime, default=datetime.datetime.utcnow)
    tempo_resposta_ms = Column(Float)

    sessao = relationship(
        "SessaoAtendimento",
        back_populates="atendimentos"
    )