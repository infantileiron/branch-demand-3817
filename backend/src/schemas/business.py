from datetime import date
from typing import Literal
from pydantic import BaseModel,Field

Branch=Literal['川北','川南','东河','西浦','新城','临港','山前','湖滨']
Model=Literal['seasonal_naive','holt']


class Login(BaseModel):email:str;password:str


class DailyInput(BaseModel):
 branch:Branch;day:date;volume:int=Field(ge=0,le=100000);note:str=Field(default='',max_length=1000)


class AppointmentInput(BaseModel):
 branch:Branch;service_day:date;quantity:int=Field(gt=0,le=100000);note:str=Field(default='',max_length=1000)
 request_id:str=Field(default='',max_length=80)


class CancelInput(BaseModel):
 quantity:int=Field(gt=0,le=100000)
 note:str=Field(default='',max_length=1000)
 request_id:str=Field(default='',max_length=80)


class RescheduleInput(BaseModel):
 service_day:date
 quantity:int|None=Field(default=None,gt=0,le=100000)
 note:str=Field(default='',max_length=1000)
 request_id:str=Field(default='',max_length=80)


class FulfilInput(BaseModel):
 day:date
 quantity:int=Field(gt=0,le=100000)
 note:str=Field(default='',max_length=1000)
 request_id:str=Field(default='',max_length=80)


class ForecastInput(BaseModel):
 name:str=Field(min_length=2,max_length=100);branch:Branch;backtest_days:int=Field(default=14,ge=7,le=21);alpha:float=Field(default=.6,ge=.01,le=.99,allow_inf_nan=False);beta:float=Field(default=.2,ge=.01,le=.99,allow_inf_nan=False)


class StaffingInput(BaseModel):
 run_id:int=Field(gt=0);capacity:int=Field(ge=1,le=1000);model:Model;note:str=Field(min_length=8,max_length=2000)
