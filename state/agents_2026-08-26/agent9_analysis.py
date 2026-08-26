import json, numpy as np, pandas as pd
bars=json.load(open('state/agents_2026-08-26/factor_bars.json'))
px=pd.DataFrame({s:pd.Series({v['t'][:10]:v['c'] for v in b}) for s,b in bars.items()})
px.index=pd.to_datetime(px.index); px=px.sort_index()
W={'SLDP':30.1,'DKNG':27.8,'HUBS':7.8,'BHVN':5.7,'AMSC':4.6,'KYTX':4.6,'PRCH':4.3,'NTLA':4.2,'ABSI':3.8,'QUBT':2.8,'AARD':2.6,'SOC':1.6}
names=list(W); w=np.array([W[n] for n in names])/100
rets=np.log(px).diff()
out={'as_of':'2026-08-26','weights':W,'window':{}}

# ---------- 1. FACTOR DECOMPOSITION ----------
R=rets.loc['2025-02-14':].dropna(subset=names+['SPY','IWM','XBI','ARKK','TLT','HYG'])
out['window']['factor']=[str(R.index[0].date()),str(R.index[-1].date()),len(R)]
def resid(y,X):
    X=np.column_stack([np.ones(len(y))]+[X[:,i] for i in range(X.shape[1])]); b=np.linalg.lstsq(X,y,rcond=None)[0]; return y-X@b
F=pd.DataFrame(index=R.index)
F['MKT']=R.SPY.values
F['SMB']=resid(R.IWM.values,R[['SPY']].values)
F['BIO']=resid(R.XBI.values,R[['SPY']].values)
F['GROWTH']=resid(R.ARKK.values,R[['SPY']].values)
F['RATES']=R.TLT.values
F['CREDIT']=resid(R.HYG.values,R[['SPY','TLT']].values)
fac=list(F.columns)
X=np.column_stack([np.ones(len(F))]+[F[c].values for c in fac])
load={}; idio={}
for n in names:
    y=R[n].values; b=np.linalg.lstsq(X,y,rcond=None)[0]; e=y-X@b
    r2=1-e.var()/y.var()
    load[n]={c:round(float(b[i+1]),3) for i,c in enumerate(fac)}
    load[n]['alpha_ann']=round(float(b[0]*252),3); load[n]['r2']=round(float(r2),3)
    load[n]['vol_ann']=round(float(y.std()*np.sqrt(252)),3); load[n]['idio_vol_ann']=round(float(e.std()*np.sqrt(252)),3)
    idio[n]=e
out['factor_loadings']=load
book_beta={c:round(float(sum(w[i]*load[n][c] for i,n in enumerate(names))),3) for c in fac}
out['book_effective_betas']=book_beta
B=np.array([[load[n][c] for c in fac] for n in names])
SigF=np.cov(F.values.T)*252
E=np.cov(np.column_stack([idio[n] for n in names]).T)*252
bw=B.T@w
var_fac=float(bw@SigF@bw); var_idio=float(w@E@w); var_tot=var_fac+var_idio
per_fac={c:round(float(bw[i]**2*SigF[i,i])/var_tot,3) for i,c in enumerate(fac)}
Sig=np.cov(R[names].values.T)*252
out['book_variance']={'total_vol_ann':round(np.sqrt(float(w@Sig@w)),3),'model_vol_ann':round(np.sqrt(var_tot),3),
  'factor_share':round(var_fac/var_tot,3),'idio_share':round(var_idio/var_tot,3),'per_factor_share_of_model_var':per_fac}
idio_contrib={n:round(float(w[i]**2*E[i,i])/var_idio,3) for i,n in enumerate(names)}
out['book_variance']['idio_contrib_by_name']=idio_contrib
C=np.corrcoef(R[names].values.T); ev=np.sort(np.linalg.eigvalsh(C))[::-1]
Wm=np.diag(w); Sw=Wm@Sig@Wm; evw=np.sort(np.linalg.eigvalsh(Sw))[::-1]
out['independent_bets']={
 'corr_matrix_top_eig_share':round(float(ev[0]/ev.sum()),3),'corr_matrix_eff_N':round(float(ev.sum()**2/(ev**2).sum()),2),
 'corr_matrix_eigs':[round(float(x),2) for x in ev[:5]],
 'weighted_cov_top_eig_share':round(float(evw[0]/evw.sum()),3),'weighted_cov_eff_N':round(float(evw.sum()**2/(evw**2).sum()),2),
 'weight_herfindahl_N':round(float(1/(w**2).sum()),2),
 'mean_pairwise_corr':round(float((C.sum()-12)/132),3),
 'risk_contribution_pct':{n:round(float(w[i]*(Sig@w)[i]/(w@Sig@w)),3) for i,n in enumerate(names)}}
out['pairwise_corr_top']=sorted([(names[i],names[j],round(float(C[i,j]),2)) for i in range(12) for j in range(i+1,12)],key=lambda x:-x[2])[:8]
out['corr_SLDP_DKNG']=round(float(C[0,1]),3)
pc1=np.linalg.eigh(C)[1][:,-1]; pc1=pc1*np.sign(pc1.sum())
out['pc1_loadings']={n:round(float(pc1[i]),3) for i,n in enumerate(names)}

# ---------- 2. JOINT CATASTROPHE ----------
def cum(s,a,b): return float(px[s].loc[b]/px[s].loc[:a].iloc[-1]-1)
def win(a,b): return {s:round(cum(s,a,b),3) for s in ['SPY','IWM','XBI','ARKK','TLT','HYG']}
apr=win('2025-02-19','2025-04-08')
out['hist_windows']={'apr2025_derating':apr}
def book_path(a,b,weights):
    p=px.loc[a:b,names].dropna(axis=1,how='all').ffill()
    ww=np.array([weights[n] for n in p.columns]); ww=ww/ww.sum()
    return (p/p.iloc[0])@ww
nav=book_path('2025-02-19','2025-04-08',W)
out['hist_windows']['apr2025_book_realised']={'terminal':round(float(nav.iloc[-1]-1),3),'min':round(float(nav.min()-1),3)}
rawf=['SPY','IWM','XBI','ARKK','TLT']
Xraw=np.column_stack([np.ones(len(R))]+[R[c].values for c in rawf])
Braw={n:np.linalg.lstsq(Xraw,R[n].values,rcond=None)[0][1:] for n in names}
out['raw_etf_loadings']={n:{c:round(float(Braw[n][i]),2) for i,c in enumerate(rawf)} for n in names}
def scen(shock):
    v=np.array([shock.get(c,0.0) for c in rawf])
    per={n:float(Braw[n]@v) for n in names}
    return per, float(sum(w[i]*per[n] for i,n in enumerate(names)))
S={}
sh={'SPY':-.08,'IWM':-.15,'XBI':-.35,'ARKK':-.20,'TLT':-.12}
per,tot=scen({k:np.log(1+v) for k,v in sh.items()})
S['S1_bio_funding_shut_rates_up']={'shock':sh,'book_pct':round(float(np.exp(tot)-1),3),'per_name_pct':{n:round(float(np.exp(x)-1),3) for n,x in per.items()}}
S2={}
for n in ['SLDP','DKNG']:
    d1=float(np.exp(rets[n].min())-1); d5=float((px[n]/px[n].shift(5)-1).min()); d1d=str(rets[n].idxmin().date())
    dd=float((px[n]/px[n].cummax()-1).min())
    S2[n]={'worst_1d':round(d1,3),'worst_1d_date':d1d,'worst_5d':round(d5,3),'max_dd_since_2024':round(dd,3),'weight':W[n]/100}
sl=idio['SLDP']; spill={}
for i,n in enumerate(names):
    if n=='SLDP': continue
    spill[n]=float(np.cov(idio[n],sl)[0,1]/sl.var())
S2['SLDP_minus60_idio']={'direct_book_pct':round(-.60*W['SLDP']/100,3),
   'spill_betas_on_SLDP_idio':{n:round(v,3) for n,v in spill.items()},
   'spill_book_pct':round(float(sum(w[i]*spill[n]*-.60 for i,n in enumerate(names) if n!='SLDP')),3)}
S2['DKNG_minus40']={'direct_book_pct':round(-.40*W['DKNG']/100,3)}
S2['both_same_month_pct']=round(-.60*W['SLDP']/100-.40*W['DKNG']/100,3)
S['S2_single_name']=S2
shock={s:np.log(1+apr[s]) for s in rawf}
per,tot=scen(shock)
S['S3_apr2025_replay']={'shock':apr,'book_pct_modelled':round(float(np.exp(tot)-1),3),'book_realised':out['hist_windows']['apr2025_book_realised'],'per_name_pct':{n:round(float(np.exp(x)-1),3) for n,x in per.items()}}
sh={'SPY':-.20,'IWM':-.25,'XBI':-.45,'ARKK':-.60,'TLT':-.20}
per,tot=scen({k:np.log(1+v) for k,v in sh.items()})
S['S3b_2022_style_growth_bust']={'shock':sh,'book_pct':round(float(np.exp(tot)-1),3),'per_name_pct':{n:round(float(np.exp(x)-1),3) for n,x in per.items()}}
bookr=(np.exp(R[names])-1)@w
out['book_worst_days']=[(str(d.date()),round(float(v),3)) for d,v in bookr.nsmallest(5).items()]
out['book_worst_20d']=round(float(((1+bookr).rolling(20).apply(np.prod)-1).min()),3)
out['scenarios']=S

# ---------- 3. SIZING ----------
P=px.loc['2025-08-01':'2026-08-25',names].dropna()
out['window']['sizing']=[str(P.index[0].date()),str(P.index[-1].date()),len(P)]
prior=rets.loc['2024-08-01':'2025-07-31',names]
iv=1/prior.std(); iv=iv/iv.sum()
def stats(nav):
    r=nav.pct_change().dropna(); dd=(nav/nav.cummax()-1).min()
    return {'terminal':round(float(nav.iloc[-1]),3),'max_dd':round(float(dd),3),'daily_vol':round(float(r.std()),4),'ann_vol':round(float(r.std()*np.sqrt(252)),3),'sharpe':round(float(r.mean()/r.std()*np.sqrt(252)),2)}
rel=P/P.iloc[0]
res={}
for label,ww in [('actual_weights',w),('equal',np.ones(12)/12),('inverse_vol',iv[names].values)]:
    bh=rel@ww; cm=(1+(P.pct_change().fillna(0)@ww)).cumprod()
    res[label]={'buy_and_hold':stats(bh),'constant_mix_daily':stats(cm),'weights':{n:round(float(x),3) for n,x in zip(names,ww)}}
res['single_names']={n:round(float(rel[n].iloc[-1]),3) for n in names}
for s in ['XBI','SPY','IWM','ARKK']:
    res[s]=round(float(px[s].loc['2026-08-25']/px[s].loc['2025-08-01']),3)
start_w=w/rel.iloc[-1].values; start_w=start_w/start_w.sum()
res['implied_start_weights_if_buy_and_hold']={n:round(float(x),3) for n,x in zip(names,start_w)}
res['implied_start_bh']=stats(rel@start_w)
# ex-top-two
mask=np.array([n not in ('SLDP','DKNG') for n in names]); w2=w*mask; w2=w2/w2.sum()
res['actual_ex_SLDP_DKNG_bh']=stats(rel@w2)
res['SLDP_DKNG_only_bh']=stats(rel@np.array([W[n]/57.9 if n in('SLDP','DKNG') else 0 for n in names]))
out['sizing']=res

# ---------- 4. ADMISSION ----------
sig=rets.loc['2026-05-26':'2026-08-25',names].std()
adm={'per_underlying_cap_15pct':{n:{'weight':W[n]/100,'refused':bool(W[n]/100>0.15)} for n in names},
 'free_cash_10pct':{'true_max_loss_frac_shares':1.0,'free_after':0.0,'refused':True},
 'theta':'0 (shares) -> passes',
 'delta_stress_2sigma_sum':{'per_name_2sig_pct':{n:round(float(2*sig[n]*W[n]/100),4) for n in names},'sigma63_daily':{n:round(float(sig[n]),4) for n in names}}}
adm['delta_stress_2sigma_sum']['book_pct']=round(float(sum(2*sig[n]*W[n]/100 for n in names)),4)
adm['delta_stress_2sigma_sum']['cap']=0.10
adm['delta_stress_2sigma_sum']['refused']=bool(adm['delta_stress_2sigma_sum']['book_pct']>0.10)
we=np.ones(12)/12; Swe=np.diag(we)@Sig@np.diag(we); eve=np.sort(np.linalg.eigvalsh(Swe))[::-1]
be=B.T@we
adm['equal_weight_same_names']={'per_name_cap':'passes (8.3%<15%)','delta_stress_2sigma':round(float(sum(2*sig[n]/12 for n in names)),4),
 'weighted_cov_top_eig_share':round(float(eve[0]/eve.sum()),3),'eff_N':round(float(eve.sum()**2/(eve**2).sum()),2),
 'factor_share':round(float(be@SigF@be/(be@SigF@be+we@E@we)),3),'book_betas':{c:round(float(be[i]),3) for i,c in enumerate(fac)},
 'ann_vol':round(float(np.sqrt(we@Sig@we)),3)}
# what fraction of the book, at 12 x 8.3%, passes every rule while carrying the same common shock
g=R.ARKK; sg=float(g.std())
bg={n:float(np.cov(R[n],g)[0,1]/g.var()) for n in names}
m1=-2.33*sg*np.sqrt(21)
adm['proposed_common_shock_test']={'proxy':'ARKK','sigma_daily':round(sg,4),'shock_1m_99pct':round(float(m1),3),
  'beta_to_proxy':{n:round(v,2) for n,v in bg.items()},
  'L_cs_actual':round(float(sum(w[i]*bg[n]*m1 for i,n in enumerate(names))),3),
  'L_cs_equal':round(float(sum(bg[n]*m1/12 for n in names)),3)}
# PC1 version: book loading on the names' own first PC, and the 99% one-month move of that PC
pc1r=R[names].values@pc1; spc=float(pc1r.std()); bpc={n:float(np.cov(R[n],pc1r)[0,1]/pc1r.var()) for n in names}
adm['proposed_common_shock_test']['pc1_version']={'pc1_sigma_daily':round(spc,4),'L_cs_actual':round(float(sum(w[i]*bpc[n]*-2.33*spc*np.sqrt(21) for i,n in enumerate(names))),3),
  'L_cs_equal':round(float(sum(bpc[n]*-2.33*spc*np.sqrt(21)/12 for n in names)),3)}
out['admission']=adm
json.dump(out,open('state/agents_2026-08-26/portfolio_factor_decomposition.json','w'),indent=1,default=str)
print(json.dumps(out,indent=1,default=str))
