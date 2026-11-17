/** @typedef {{id:number,branch:string,day:string,volume:number,fulfilled:number,scatter:number,note:string}} DailyVolume */
/** @typedef {{id:number,branch:string,service_day:string,quantity:number,cancelled:number,fulfilled:number,moved_out:number,remaining:number,status:string,note:string,rescheduled_from:?number}} AppointmentBatch */
/** @typedef {{id:number,batch_id:number,branch:string,day:string,quantity:number,note:string}} Fulfilment */
/** @typedef {{id:number,name:string,branch:string,revision:number,backtest_days:number,alpha:number,beta:number,state:string,result:object}} ForecastRun */
/** @typedef {{day:string,scatter:number,reserved:number,total:number,staff:number}} ScheduleDay */
/** @typedef {{id:number,run_id:number,branch:string,revision:number,capacity:number,model:string,schedule:ScheduleDay[],basis:object,status:string,approved_by:string,approved_at:string,invalid_reason:string}} Staffing */
