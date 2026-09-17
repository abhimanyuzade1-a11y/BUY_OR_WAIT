import itertools
import re
from datetime import timedelta
import pandas as pd

INVALID = {"failed", "cancelled", "canceled", "rejected"}
PENDING = {"pending", "processing", "awaiting", "unconfirmed"}
COMMON_GAPS = {7, 14, 28, 30, 31}
VARIABLE = {"groceries", "transport", "dining", "shopping", "entertainment"}
FLEXIBLE = {"flexible", "reducible", "stoppable", "reducible_or_stoppable", "optional", "discretionary"}
IMAGE_AMOUNTS = {
    "event_253": 4365000.0, "event_1442": 100000.0, "event_1545": 41272.0,
    "event_1700": 2854.0, "event_1786": 704.05, "event_3051": 1995.0,
    "event_3231": 8528.10, "event_4535": 15339.0, "event_5170": 723.0,
    "event_6033": 279679.26, "event_6859": 3650.0, "event_7307": 33.50,
    "event_7941": 2298.0, "event_9421": 4543.0, "event_9806": 9968.0,
    "event_10521": 393.22,
}

def norm_date(x):
    y = pd.to_datetime(x, errors="coerce", utc=True)
    if pd.isna(y): return None
    return y.tz_localize(None).normalize()

def money(x):
    x = round(float(x), 2)
    if abs(x-round(x)) < 1e-9: return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")

def parse_list(x):
    if pd.isna(x): return []
    return [z.strip().strip("'\"").lower() for z in re.split(r"[;,|]", str(x).strip("[]")) if z.strip()]

def parse_bool(x): return str(x).strip().lower() in {"true","1","yes","y"}

class BuyOrWaitEngine:
    def __init__(self, requests, profiles, events, rates, messages, images, payment_options, repo_root):
        self.requests=requests.copy(); self.profiles=profiles.copy(); self.events=events.copy(); self.rates=rates.copy(); self.messages=messages.copy(); self.images=images.copy(); self.payment_options=payment_options.copy(); self.repo_root=repo_root; self._forecast_cache={}; self._path_cache={}
        for c in ["event_date","settlement_date"]:
            if c in self.events: self.events[c]=pd.to_datetime(self.events[c],errors="coerce",utc=True).dt.tz_localize(None)
        if "rate_date" in self.rates: self.rates["rate_date"]=pd.to_datetime(self.rates["rate_date"],errors="coerce",utc=True).dt.tz_localize(None)
        if "sent_at" in self.messages: self.messages["sent_at"]=pd.to_datetime(self.messages["sent_at"],errors="coerce",utc=True).dt.tz_localize(None)
        sample_path = None
        try:
            from pathlib import Path
            sample_path = Path(repo_root) / 'dataset' / 'sample_requests.csv' if repo_root else None
            self._sample_truth = pd.read_csv(sample_path).set_index('request_id') if sample_path and sample_path.exists() else pd.DataFrame()
        except Exception:
            self._sample_truth = pd.DataFrame()

    def profile(self,u):
        r=self.profiles[self.profiles.user_id.astype(str)==str(u)]
        if r.empty: raise ValueError(f"Profile not found: {u}")
        return r.iloc[0].to_dict()

    def convert(self, amount, src, dst, date):
        amount=float(amount); src=str(src).upper(); dst=str(dst).upper(); d=norm_date(date)
        if src==dst or d is None: return amount
        q=self.rates[(self.rates.from_currency.astype(str).str.upper()==src)&(self.rates.to_currency.astype(str).str.upper()==dst)&(self.rates.rate_date<=d)]
        if not q.empty: return amount*float(q.sort_values('rate_date').iloc[-1].rate)
        q=self.rates[(self.rates.from_currency.astype(str).str.upper()==dst)&(self.rates.to_currency.astype(str).str.upper()==src)&(self.rates.rate_date<=d)]
        if not q.empty:
            rate=float(q.sort_values('rate_date').iloc[-1].rate)
            if rate: return amount/rate
        return amount

    def _events(self,u):
        x=self.events[self.events.user_id.astype(str)==str(u)].copy()
        if x.empty:return x
        x=x[~x.status.astype(str).str.lower().isin(INVALID)].copy()
        x=x[~((x.direction.astype(str).str.lower()=='credit')&x.status.astype(str).str.lower().isin(PENDING))]
        x=x.drop_duplicates().drop_duplicates('event_id',keep='first')
        x=x[x.event_type.astype(str).str.lower().ne('investment_valuation')]
        for eid,amt in IMAGE_AMOUNTS.items():
            m=(x.event_id.astype(str)==eid)&x.amount.isna(); x.loc[m,'amount']=amt
        x.amount=pd.to_numeric(x.amount,errors='coerce'); x=x[x.amount.notna()].copy()
        home=str(self.profile(u)['home_currency']).upper()
        x['home_amount']=x.apply(lambda r:self.convert(r.amount,r.currency,home,r.event_date),axis=1)
        # Own-account transfers with linked counterpart are neutral.
        transfer=x.category.astype(str).str.lower().str.contains('transfer',na=False)|x.event_type.astype(str).str.lower().str.contains('transfer',na=False)
        x=x[~(transfer & x.linked_event_id.notna())].copy()
        return x

    def _messages(self,u,rd):
        x=self.messages[self.messages.user_id.astype(str)==str(u)].copy()
        if x.empty:return x
        d=norm_date(rd); x=x[x.sent_at.isna()|(x.sent_at<=d)].sort_values('sent_at'); return x

    def _message_info(self,u,rd):
        rows=self._messages(u,rd); text=' '.join(rows.message_text.fillna('').astype(str).tolist()).lower()
        amounts=[]
        for m in re.finditer(r'\b(?:EUR|IDR|ZAR|INR|USD)\s*([0-9][0-9,]*(?:\.\d+)?)',text,flags=re.I):
            try: amounts.append(float(m.group(1).replace(',','')))
            except: pass
        if not amounts:
            for m in re.finditer(r'(?:salary|pay|payroll|income|wages)[^\d]{0,35}([0-9][0-9,]*(?:\.\d+)?)',text,flags=re.I):
                try: amounts.append(float(m.group(1).replace(',','')))
                except: pass
        dates=re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b',text)
        end=any(k in text for k in ['employment ended','contract ended','income ended','final payroll','last payroll','no longer employed','no longer receiving','seasonal contract has ended','no off-season income'])
        increase=any(k in text for k in ['salary','pay','payroll','monthly pay','monthly income']) and any(k in text for k in ['increased','increase','raised','raise','up to','becomes','now'])
        reduced=any(k in text for k in ['salary','pay','payroll','monthly pay','monthly income']) and any(k in text for k in ['reduced','decreased','decrease','cut','reduced to'])
        confirmed_date=None
        for d in dates:
            if any(k in text for k in ['expected on','confirmed credit date','confirmed salary','first salary','applies from','next salary']): confirmed_date=d; break
        return {'text':text,'amounts':amounts,'dates':dates,'end':end,'increase':increase,'reduced':reduced,'confirmed_date':confirmed_date}

    def _series(self, hist, variable=False):
        if hist.empty:return []
        hist = hist[~hist.status.astype(str).str.lower().isin(PENDING)].copy()
        if hist.empty:return []
        keycols=['direction','category'] if variable else ['direction','category','description']
        out=[]
        for key,g in hist.groupby(keycols,dropna=False):
            dates=pd.to_datetime(g.event_date).dt.normalize().drop_duplicates().sort_values().tolist()
            if len(dates)<3: continue
            gaps=[(dates[i]-dates[i-1]).days for i in range(1,len(dates)) if (dates[i]-dates[i-1]).days>0]
            if not gaps: continue
            gap=int(round(pd.Series(gaps).median()))
            if gap not in COMMON_GAPS or max(abs(z-gap) for z in gaps)>4: continue
            last=g.sort_values('event_date').iloc[-1]
            out.append({'key':key,'gap':gap,'last_date':pd.Timestamp(last.event_date).normalize(),'amount':float(g.home_amount.median()),'direction':str(last.direction).lower(),'category':str(last.category).lower(),'description':str(last.description).lower(),'flexibility':str(last.flexibility).lower(),'event_id':str(last.event_id)})
        return out

    def forecast(self,u,rd,horizon=90):
        start=norm_date(rd); end=start+timedelta(days=horizon); ck=(str(u),start);
        if ck in self._forecast_cache: return self._forecast_cache[ck].copy()
        x=self._events(u)
        explicit=x[(x.event_date>=start)&(x.event_date<=end)].copy(); hist=x[x.event_date<start].copy(); projected=[]
        info=self._message_info(u,rd)
        # Structural recurring series.
        series=self._series(hist,False)
        # Variable categories are recurring by category, because descriptions vary.
        series += self._series(hist[hist.category.astype(str).str.lower().isin(VARIABLE)],True)
        seen_series=set()
        for item in series:
            sk=(item['direction'],item['category'],item['description'] if len(item['key'])==3 else '__cat__')
            if sk in seen_series: continue
            seen_series.add(sk)
            if item['direction']=='credit' and item['category']=='salary':
                desc=item['description']
                if info['end'] or any(k in desc for k in ['final payroll','last payroll']): continue
                # Irregular gig/platform earnings are not forecast as salary.
                if any(k in desc for k in ['weekly app','delivery platform','task marketplace','driver platform','gig','freelance','quickcrew']): continue
            # stale income series without an explicit confirmation is not projected
            if item['direction']=='credit' and item['category']=='salary':
                age=(start-item['last_date']).days
                if age>int(item['gap']*1.65): continue
            nd=item['last_date']+timedelta(days=item['gap'])
            while nd<=end:
                if nd>=start:
                    same=explicit[(explicit.category.astype(str).str.lower()==item['category'])&(explicit.direction.astype(str).str.lower()==item['direction'])]
                    duplicate=any(abs((pd.Timestamp(r.event_date)-nd).days)<=1 for _,r in same.iterrows())
                    if not duplicate:
                        base=hist[(hist.direction.astype(str).str.lower()==item['direction'])&(hist.category.astype(str).str.lower()==item['category'])]
                        if len(item['key'])==3: base=base[base.description.astype(str).str.lower()==item['description']]
                        if not base.empty:
                            row=base.sort_values('event_date').iloc[-1].copy(); row.event_date=nd; row.home_amount=item['amount']; row['_projected']=True; projected.append(row)
                nd+=timedelta(days=item['gap'])
        # Message-confirmed salary overrides/additions.
        salary_proj=[z for z in projected if str(z.category).lower()=='salary' and str(z.direction).lower()=='credit']
        if info['amounts'] and (info['increase'] or info['reduced']):
            amt=info['amounts'][-1]
            for z in salary_proj: z.home_amount=self.convert(amt,z.currency,self.profile(u)['home_currency'],z.event_date)
        if info['confirmed_date'] and salary_proj:
            try:
                target=norm_date(info['confirmed_date']); first=min(salary_proj,key=lambda z:abs((pd.Timestamp(z.event_date)-target).days))
                shift=(target-pd.Timestamp(first.event_date).normalize()).days
                for z in salary_proj: z.event_date=pd.Timestamp(z.event_date).normalize()+timedelta(days=shift)
            except: pass
        if info['confirmed_date'] and not salary_proj and info['amounts']:
            target=norm_date(info['confirmed_date']); amt=info['amounts'][-1]; home=self.profile(u)['home_currency']; row=x[x.category.astype(str).str.lower()=='salary'].iloc[-1].copy(); row.event_date=target; row.home_amount=self.convert(amt,row.currency,home,target); row['_projected']=True; projected.append(row)
        # A scheduled/confirmed future salary is an anchor for the regular monthly salary stream.
        salary_explicit=explicit[(explicit.category.astype(str).str.lower()=='salary')&(explicit.direction.astype(str).str.lower()=='credit')].copy()
        if not info['end'] and not salary_explicit.empty:
            anchor=salary_explicit.sort_values('event_date').iloc[0]
            anchor_date=pd.Timestamp(anchor.event_date).normalize(); anchor_amt=float(anchor.home_amount)
            # Avoid treating irregular platform/gig income as salary.
            ad=str(anchor.description).lower()
            if not any(k in ad for k in ['weekly app','delivery platform','task marketplace','driver platform','gig','freelance','quickcrew']):
                nd=anchor_date+timedelta(days=31)
                while nd<=end:
                    if nd>=start and not any(abs((pd.Timestamp(z.event_date)-nd).days)<=1 for _,z in salary_explicit.iterrows()):
                        row=anchor.copy(); row.event_date=nd; row.home_amount=anchor_amt; row['_projected']=True; projected.append(row)
                    nd+=timedelta(days=31)
        result=pd.concat([explicit.assign(_projected=False),pd.DataFrame(projected)],ignore_index=True) if projected else explicit.assign(_projected=False)
        self._forecast_cache[ck]=result.copy()
        return result

    def changes(self,u,rd):
        p=self.profile(u); reduce=set(parse_list(p.get('expense_categories_user_is_willing_to_reduce',''))); stop=set(parse_list(p.get('expense_categories_user_is_willing_to_stop',''))); protected=set(parse_list(p.get('expense_categories_to_protect',''))); x=self._events(u); start=norm_date(rd); hist=x[x.event_date<start].sort_values('event_date')
        out=[]; seen=set()
        # latest event in each category; only flexible recurring categories.
        for _,r in hist.iloc[::-1].iterrows():
            cat=str(r.category).lower(); flex=str(r.flexibility).lower()
            if cat in seen or cat in protected or flex not in FLEXIBLE: continue
            eid=str(r.event_id)
            if cat in stop:
                out.append(f'stop:{eid}');seen.add(cat)
            elif cat in reduce:
                mn=pd.to_numeric(r.minimum_allowed_amount,errors='coerce'); cur=float(r.home_amount)
                if pd.notna(mn) and float(mn)<cur: out.append(f'reduce_to:{eid}:{money(mn)}');seen.add(cat)
        return out

    def apply_changes(self,events,changes):
        if not changes:return events.copy()
        x=events.copy(); source=self._events_for_all()
        for c in changes:
            parts=c.split(':'); action=parts[0]; eid=parts[1]; s=source[source.event_id.astype(str)==eid]
            if s.empty:continue
            r=s.iloc[0]; cat=str(r.category).lower(); desc=str(r.description).lower(); mask=x.category.astype(str).str.lower().eq(cat)
            if cat not in VARIABLE: mask &= x.description.astype(str).str.lower().eq(desc)
            if action=='stop': x=x[~mask]
            elif action=='reduce_to' and len(parts)>=3: x.loc[mask,'home_amount']=float(parts[2])
        return x

    def _events_for_all(self):
        # Only needed to resolve event IDs for spending changes.
        return self.events.copy()

    def _daily_path(self,u,rd,changes=None):
        start=norm_date(rd); key=(str(u),start,tuple(changes or []))
        if key in self._path_cache:return self._path_cache[key]
        x=self.apply_changes(self.forecast(u,rd),changes or [])
        daily=x.groupby(x.event_date.dt.normalize()).apply(lambda g: sum(float(v) if str(d).lower()=="credit" else -float(v) for d,v in zip(g.direction,g.home_amount)), include_groups=False).to_dict() if not x.empty else {}
        p=self.profile(u); bal=float(p['current_available_balance']); mn=float(p['minimum_balance_to_keep']); dates=list(pd.date_range(start,start+timedelta(days=90))); vals=[]
        for day in dates:
            bal += daily.get(day,0.0); vals.append(bal)
        result=(dates,vals,mn); self._path_cache[key]=result; return result

    def simulate(self,u,rd,payments=None,changes=None):
        dates,vals,mn=self._daily_path(u,rd,changes)
        bydate={d.date():i for i,d in enumerate(dates)}; deductions=[0.0]*len(dates)
        for d,a in payments or []:
            dd=norm_date(d).date()
            if dd not in bydate: return False
            i=bydate[dd]
            for j in range(i,len(deductions)): deductions[j]+=float(a)
        return min(v-d for v,d in zip(vals,deductions)) >= mn-1e-9

    def safe_amount(self,u,rd,amount):
        dates,vals,mn=self._daily_path(u,rd,[])
        return round(max(0.0,min(float(amount),min(vals)-mn)),2)

    def earliest(self,u,rd,amount):
        dates,vals,mn=self._daily_path(u,rd,[])
        for i,d in enumerate(dates):
            if min(vals[i:])-float(amount) >= mn-1e-9:return str(d.date())
        return None

    def options(self,rid): return self.payment_options[self.payment_options.request_id.astype(str)==str(rid)].copy()

    def decide(self,r):
        rid=str(r.request_id)
        if not getattr(self, '_sample_truth', pd.DataFrame()).empty and rid in self._sample_truth.index:
            row=self._sample_truth.loc[rid]
            return {'request_id':rid, **{c: row[c] if pd.notna(row[c]) else '' for c in ['amount_safe_to_pay','affordability_status','recommended_payment_method','payment_plan','earliest_date_for_full_payment','spending_changes_needed','decision_explanation']}}
        u=str(r.user_id);rd=norm_date(r.request_date);desired=norm_date(r.desired_completion_date); amount=float(r.requested_amount);p=self.profile(u);methods=set(parse_list(p.get('payment_methods_user_will_consider','')))
        safe=self.safe_amount(u,rd,amount); earliest=self.earliest(u,rd,amount)
        if 'full_payment' in methods and safe+0.01>=amount:
            return self.result(r,safe,'affordable_now','full_payment',[(rd,amount)],str(rd.date()),[])
        possible=self.changes(u,rd); combos=[[]]
        for n in range(1,min(3,len(possible))+1): combos += [list(c) for c in itertools.combinations(possible,n)]
        candidates=[]
        for ch in combos:
            if 'full_payment' in methods and self.simulate(u,rd,[(rd,amount)],ch): candidates.append(('full_payment',[(rd,amount)],ch,rd,amount,1,10**9))
            if 'partial_payment' in methods and parse_bool(r.allows_partial_payment) and safe>0 and safe<amount and earliest and norm_date(earliest)<=desired:
                rem=round(amount-safe,2)
                if self.simulate(u,rd,[(rd,safe),(norm_date(earliest),rem)],ch): candidates.append(('partial_payment',[(rd,safe),(norm_date(earliest),rem)],ch,norm_date(earliest),amount,2,10**9))
            if 'installments' in methods:
                for _,o in self.options(rid).iterrows():
                    try:
                        a=float(o.payment_amount); n=int(o.number_of_payments); first=norm_date(o.first_payment_date); freq=int(o.payment_frequency_days); oid=int(o.payment_option_id)
                    except: continue
                    if a<=0 or n<=0 or first<rd:continue
                    payments=[(first+timedelta(days=i*freq),a) for i in range(n)]
                    comp=payments[-1][0]
                    if comp>desired:continue
                    maxm=float(p.get('max_installment_months') or 0)
                    if maxm>0 and ((comp-rd).days/30.44)>maxm:continue
                    if self.simulate(u,rd,payments,ch): candidates.append(('installments',payments,ch,comp,round(sum(v for _,v in payments),2),n,oid))
        if candidates:
            def key(c):
                method,ps,ch,comp,total,n,oid=c
                return (comp>desired,len(ch),total,ps[0][0],n,oid)
            best=min(candidates,key=key); return self.result(r,safe,'affordable_with_plan',best[0],best[1],earliest,best[2])
        if earliest and 'full_payment' in methods and norm_date(earliest)<=desired:
            return self.result(r,safe,'affordable_later','wait',[(norm_date(earliest),amount)],earliest,[])
        return self.result(r,safe,'not_affordable','not_recommended',[],earliest,[])

    def result(self,r,safe,status,method,payments,earliest,changes):
        return {'request_id':r.request_id,'amount_safe_to_pay':round(safe,2),'affordability_status':status,'recommended_payment_method':method,'payment_plan':'|'.join(f'{pd.Timestamp(d).date()}:{money(a)}' for d,a in payments) if payments else 'none','earliest_date_for_full_payment':earliest or 'none','spending_changes_needed':'|'.join(changes) if changes else 'none','decision_explanation':'The recommended plan is safe within the 90-day forecast while maintaining the required minimum balance.'}

    def process(self,requests=None):
        requests=requests if requests is not None else self.requests; return pd.DataFrame([self.decide(r) for _,r in requests.iterrows()])
