"""Validate against a separately supplied reference CSV; never fabricate calibration."""
import argparse,csv,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.physics.leakage import NominalDevice,OperatingPoint,compute_leakage

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('csv');p.add_argument('--source',required=True);p.add_argument('--reference-kind',choices=['simulation','measurement'],required=True);p.add_argument('--limit-A',type=float,required=True);p.add_argument('--output',default='reference-validation.json');args=p.parse_args()
    rows=list(csv.DictReader(open(args.csv))); predictions=[];actual=[]
    for row in rows:
        # Dataset must define a held-out split; no fitting is done by this tool.
        if row.get('split')!='validation':continue
        pred,_=compute_leakage(float(row['delta_L_nm']),float(row['delta_tox_nm']),float(row['delta_vth_mV']),OperatingPoint(temperature_K=float(row['temperature_K'])),NominalDevice())
        ref=float(row['Ioff_A'])
        if not np.isfinite(ref) or ref<=0:raise ValueError('Reference currents must be finite and positive')
        predictions.append(pred);actual.append(ref)
    if not actual:raise ValueError('CSV requires held-out rows with split=validation')
    pred=np.array(predictions);ref=np.array(actual)
    out=dict(source=args.source,reference_kind=args.reference_kind,validation_samples=len(ref),fitting='None; existing illustrative coefficients unchanged',
        median_relative_error=float(np.median(abs(pred-ref)/ref)),max_relative_error=float(np.max(abs(pred-ref)/ref)),
        rms_log_error=float(np.sqrt(np.mean(np.log(pred/ref)**2))),
        leakage_classification_disagreement=float(np.mean((pred>=args.limit_A)!=(ref>=args.limit_A))),
        near_boundary_count=int(np.sum(abs(ref-args.limit_A)<=.1*args.limit_A)),
        note='Agreement with a simulation reference does not establish fabricated-device accuracy.')
    Path(args.output).write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
