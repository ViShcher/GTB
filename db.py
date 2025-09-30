from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


# МОДЕЛИ


class MuscleGroup(SQLModel, table=True):
id: Optional[int] = Field(default=None, primary_key=True)
name: str
slug: str
exercises: List["Exercise"] = Relationship(back_populates="primary_muscle")


class Equipment(SQLModel, table=True):
id: Optional[int] = Field(default=None, primary_key=True)
name: str


class Exercise(SQLModel, table=True):
id: Optional[int] = Field(default=None, primary_key=True)
name: str
type: str = Field(description="strength | cardio | mobility | stretch | circuit")
primary_muscle_id: Optional[int] = Field(default=None, foreign_key="musclegroup.id")
primary_muscle: Optional[MuscleGroup] = Relationship(back_populates="exercises")
equipment_id: Optional[int] = Field(default=None, foreign_key="equipment.id")


class Workout(SQLModel, table=True):
id: Optional[int] = Field(default=None, primary_key=True)
user_id: int
title: str


class WorkoutItem(SQLModel, table=True):
id: Optional[int] = Field(default=None, primary_key=True)
workout_id: int = Field(foreign_key="workout.id")
exercise_id: int = Field(foreign_key="exercise.id")
# Параметры под силовые/кардио: повторения, подходы, вес, время, дистанция
sets: Optional[int] = None
reps: Optional[int] = None
weight: Optional[float] = None
duration_sec: Optional[int] = None
distance_m: Optional[int] = None


# АСИНХРОННЫЙ ДВИЖОК


_engine: Optional[AsyncEngine] = None


async def get_engine(database_url: str) -> AsyncEngine:
global _engine
if _engine is None:
_engine = create_async_engine(database_url, echo=False, future=True)
return _engine


async def init_db(database_url: str):
engine = await get_engine(database_url)
async with engine.begin() as conn:
await conn.run_sync(SQLModel.metadata.create_all)


async def get_session(database_url: str) -> AsyncSession:
engine = await get_engine(database_url)
return AsyncSession(engine)
