from __future__ import annotations
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import JSON,Boolean,DateTime,Float,ForeignKey,Index,Integer,String,Text,UniqueConstraint
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column
def utcnow():return datetime.now(timezone.utc)
class Base(DeclarativeBase):pass
class Timestamped:
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
class User(Timestamped,Base):
    __tablename__='users';email:Mapped[str|None]=mapped_column(String(320),unique=True);display_name:Mapped[str]=mapped_column(String(200))
class PersonalProfileRecord(Timestamped,Base):
    __tablename__='personal_profiles';user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'),unique=True);headline:Mapped[str]=mapped_column(String(300));profile_json:Mapped[dict]=mapped_column(JSON);version:Mapped[int]=mapped_column(Integer,default=1)
class MemoryItemRecord(Timestamped,Base):
    __tablename__='memory_items';__table_args__=(UniqueConstraint('user_id','category','key',name='uq_memory_user_category_key'),Index('ix_memory_user_category','user_id','category'));user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'));category:Mapped[str]=mapped_column(String(80));key:Mapped[str]=mapped_column(String(180));value_json:Mapped[dict]=mapped_column(JSON);source:Mapped[str]=mapped_column(String(40));confidence:Mapped[float]=mapped_column(Float);expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));is_user_overridden:Mapped[bool]=mapped_column(Boolean,default=False)
class CompanyRecord(Timestamped,Base):
    __tablename__='companies';name:Mapped[str]=mapped_column(String(250));website:Mapped[str|None]=mapped_column(String(2048));company_json:Mapped[dict]=mapped_column(JSON)
class OpportunityRecord(Timestamped,Base):
    __tablename__='opportunities';__table_args__=(Index('ix_opportunities_user_status','user_id','status'),);user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'));company_id:Mapped[str|None]=mapped_column(String(36),ForeignKey('companies.id'));source_url:Mapped[str|None]=mapped_column(String(2048));raw_text:Mapped[str|None]=mapped_column(Text);opportunity_json:Mapped[dict]=mapped_column(JSON);status:Mapped[str]=mapped_column(String(40))
class EvidenceClaimRecord(Timestamped,Base):
    __tablename__='evidence_claims';opportunity_id:Mapped[str]=mapped_column(String(36),ForeignKey('opportunities.id'));claim:Mapped[str]=mapped_column(Text);claim_type:Mapped[str]=mapped_column(String(40));source_url:Mapped[str|None]=mapped_column(String(2048));supporting_excerpt:Mapped[str]=mapped_column(Text);confidence:Mapped[float]=mapped_column(Float)
class AnalysisRunRecord(Timestamped,Base):
    __tablename__='analysis_runs';user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'));opportunity_id:Mapped[str]=mapped_column(String(36),ForeignKey('opportunities.id'));orchestrator:Mapped[str]=mapped_column(String(40));model_metadata_json:Mapped[dict]=mapped_column(JSON);result_json:Mapped[dict]=mapped_column(JSON);status:Mapped[str]=mapped_column(String(40))
class BehaviourEventRecord(Timestamped,Base):
    __tablename__='behaviour_events';__table_args__=(Index('ix_behaviour_user_type','user_id','event_type'),);user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'));analysis_run_id:Mapped[str|None]=mapped_column(String(36),ForeignKey('analysis_runs.id'));event_type:Mapped[str]=mapped_column(String(80));event_json:Mapped[dict]=mapped_column(JSON);explicit:Mapped[bool]=mapped_column(Boolean)
class OutcomeRecord(Timestamped,Base):
    __tablename__='outcomes';user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id'));opportunity_id:Mapped[str]=mapped_column(String(36),ForeignKey('opportunities.id'));outcome_type:Mapped[str]=mapped_column(String(80));outcome_json:Mapped[dict]=mapped_column(JSON)
