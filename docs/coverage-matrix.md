# Jobre — 78-Platform Coverage & Verification Matrix

**Generated At (UTC):** `2026-11-14T15:14:53.311430+00:00`  
**Total Required Platforms:** `78` (58 ATS + 20 Job Boards)  
**Status Summary:** `{"NOT_IMPLEMENTED": 56, "VERIFIED": 22}`

> **Verification Integrity Rule:** A platform is marked `VERIFIED` **only** when its connector has executed against a real live public source, stored compressed raw snapshots, normalized valid job listings into PostgreSQL, and recorded cryptographic verification evidence.

| # | Platform | Category | Connector Key | Status | Sources | Jobs Indexed | Active Jobs | Verified Run ID | Example Live Source | Extraction Method |
|---:|---|---|---|---|---:|---:|---:|---|---|---|
| 1 | **ADP** | ATS | `adp` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | ADP WorkforceNow Career Center JSON endpoint (/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions) |
| 2 | **ApplicantPro** | ATS | `applicantpro` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML listing + schema.org JobPosting JSON-LD / XML feed |
| 3 | **Ashby** | ATS | `ashby` | **VERIFIED** | 2 | 35 | 35 | `8d9e5223` | https://jobs.ashbyhq.com/tldr.tech | Official Public Posting JSON API (https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true) |
| 4 | **Avature** | ATS | `avature` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Portal RSS/XML feed (/SearchJobs/feed) or paginated HTML portal extraction |
| 5 | **BambooHR** | ATS | `bamboohr` | **VERIFIED** | 1 | 3 | 3 | `8b122a7b` | https://elasticpath.bamboohr.com/careers | Public Career Portal JSON API (GET https://{slug}.bamboohr.com/careers/list + /careers/{id}/detail) |
| 6 | **BrassRing** | ATS | `brassring` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Infinite BrassRing TGnewUI SearchJobs JSON POST API with session cookie |
| 7 | **Breezy HR** | ATS | `breezy_hr` | **VERIFIED** | 1 | 10 | 10 | `5ec5ba00` | https://ishir.breezy.hr/ | Public JSON Feed (https://{slug}.breezy.hr/json) with optional detail JSON-LD enrichment |
| 8 | **CSOD** | ATS | `csod` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Cornerstone OnDemand Career Site JSON search endpoint |
| 9 | **CareerPlug** | ATS | `careerplug` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML career board + JobPosting JSON-LD |
| 10 | **Comeet** | ATS | `comeet` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Comeet Public Careers API v2 (/careers-api/2.0/company/{uid}/positions?token={public_token}) or embedded COMPANY_POSITIONS_DATA |
| 11 | **Dayforce** | ATS | `dayforce` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Dayforce HCM Candidate Portal Next.js / JSON search API |
| 12 | **Deel** | ATS | `deel` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public career board JSON / Ashby-backed integration where configured |
| 13 | **Dover** | ATS | `dover` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Dover public careers portal JSON / Next.js hydration payload |
| 14 | **Eightfold AI** | ATS | `eightfold_ai` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | PCSX Career Portal JSON API (/api/apply/v2/jobs) when authorized or public career page |
| 15 | **FirstStage** | ATS | `firststage` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML / embedded JSON job listings |
| 16 | **Freshteam** | ATS | `freshteam` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public Jobs Widget JSON (/hire/widgets/jobs.json) or HTML board |
| 17 | **Gem.com** | ATS | `gem` | **VERIFIED** | 1 | 25 | 25 | `af1034e0` | https://jobs.gem.com/nominal | Official Public Job Board JSON API (https://api.gem.com/job_board/v0/{slug}/job_posts) |
| 18 | **GoHire** | ATS | `gohire` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public career page HTML + JSON-LD JobPosting |
| 19 | **Greenhouse** | ATS | `greenhouse` | **VERIFIED** | 2 | 50 | 50 | `0fa16814` | https://boards.greenhouse.io/pelago | Official Public Job Board API v1 (https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true) |
| 20 | **HiBob** | ATS | `hibob` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | HiBob Public Career Site JSON API (/api/career-site/job-ad) |
| 21 | **HireBridge** | ATS | `hirebridge` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public XML/RSS feed or HTML portal listing by cid |
| 22 | **HireHive** | ATS | `hirehive` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | HireHive Public Jobs API (/api/v1/jobs) or HTML + JSON-LD |
| 23 | **Hireology** | ATS | `hireology` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Hireology public careers API / HTML + JSON-LD |
| 24 | **HiringThing** | ATS | `hiringthing` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public RSS/Atom feed or HTML job board |
| 25 | **JOIN.com** | ATS | `join_com` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Next.js __NEXT_DATA__ / JobPosting JSON-LD on public company pages |
| 26 | **JazzHR** | ATS | `jazzhr` | **VERIFIED** | 1 | 4 | 4 | `142d8b6f` | https://betterrx.applytojob.com/apply | Public Career Portal HTML listing + schema.org JobPosting JSON-LD detail extraction |
| 27 | **Jobvite** | ATS | `jobvite` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public Career Portal HTML / XML feed + JobPosting JSON-LD |
| 28 | **Kula.ai** | ATS | `kula_ai` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Kula ATS public career board JSON / SSR data |
| 29 | **Lever.co** | ATS | `lever` | **VERIFIED** | 2 | 12 | 12 | `5c8b64f2` | https://jobs.lever.co/sep | Official Public Postings JSON API v0 (https://api.lever.co/v0/postings/{slug}?mode=json) |
| 30 | **Manatal** | ATS | `manatal` | **VERIFIED** | 1 | 12 | 12 | `3c46e2ea` | https://www.careers-page.com/bridgepoint-works | Public Career Page REST API (https://www.careers-page.com/api/v1.0/c/{slug}/jobs/) |
| 31 | **Oracle Recruiting** | ATS | `oracle_recruiting` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Oracle HCM Cloud Public REST API (/hcmRestApi/resources/latest/recruitingCEJobRequisitions) |
| 32 | **PageUp** | ATS | `pageup` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | PageUp Public RSS/JSON feed or career portal HTML |
| 33 | **Paradox** | ATS | `paradox` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Paradox career site JSON search API / sitemap + JobPosting JSON-LD |
| 34 | **Paycom** | ATS | `paycom` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Paycom ATS Career Portal HTML + JobPosting JSON-LD |
| 35 | **Paycor** | ATS | `paycor` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Paycor Recruiting Newton career HTML / RSS feed |
| 36 | **Paylocity** | ATS | `paylocity` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Embedded window.pageData JSON object on public recruiting board |
| 37 | **Personio** | ATS | `personio` | **VERIFIED** | 1 | 3 | 3 | `1456f22f` | https://personio-gmbh.jobs.personio.de/ | Official Public XML Job Feed (https://{slug}.jobs.personio.de/xml?language=en) |
| 38 | **Phenom People** | ATS | `phenom_people` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Phenom People /widgets POST API (eagerLoadRefineSearch) or phApp.ddo hydration JSON |
| 39 | **Pinpoint** | ATS | `pinpoint` | **VERIFIED** | 1 | 20 | 20 | `0f283300` | https://ardentprinciples.pinpointhq.com/ | Official Public JSON Feed (https://{slug}.pinpointhq.com/postings.json) |
| 40 | **Polymer** | ATS | `polymer` | **VERIFIED** | 2 | 2 | 2 | `9f540896` | https://jobs.polymer.co/lighten | Official Public Organization Jobs JSON API (https://api.polymer.co/v1/hire/organizations/{slug}/jobs) |
| 41 | **Recooty** | ATS | `recooty` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public career page HTML + JSON-LD |
| 42 | **Recruitee** | ATS | `recruitee` | **VERIFIED** | 2 | 26 | 26 | `4c2ad4be` | https://reploidgroupag.recruitee.com/ | Official Public Careers API (https://{slug}.recruitee.com/api/offers/) |
| 43 | **Rippling** | ATS | `rippling` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Rippling ATS public board API / Cloudflare-protected Next.js page |
| 44 | **Rival** | ATS | `rival` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | SilkRoad / Rival OpenHire XML feed or career portal HTML |
| 45 | **SAP SuccessFactors** | ATS | `sap_successfactors` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Recruiting Marketing (RMK) XML Sitemap + HTML/JSON-LD job pages |
| 46 | **SmartRecruiters** | ATS | `smartrecruiters` | **VERIFIED** | 1 | 15 | 15 | `a50f857e` | https://careers.smartrecruiters.com/BoschGroup | Official Public Posting API v1 (https://api.smartrecruiters.com/v1/companies/{slug}/postings) |
| 47 | **Taleo** | ATS | `taleo` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Oracle Taleo Career Section RSS feed orftlinterface JSON POST |
| 48 | **Teamtailor** | ATS | `teamtailor` | **VERIFIED** | 1 | 20 | 20 | `2e8b4681` | https://career.teamtailor.com/jobs | Official Public RSS 2.0 Feed (/jobs.rss with xmlns:tt location & department metadata) |
| 49 | **Trakstar** | ATS | `trakstar` | **VERIFIED** | 1 | 15 | 15 | `0e9dbe97` | https://whatfix101.hire.trakstar.com/ | Public Career Portal HTML + schema.org JobPosting JSON-LD detail extraction |
| 50 | **TriNet** | ATS | `trinet` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML career board extraction |
| 51 | **UltiPro** | ATS | `ultipro` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | UKG Pro / UltiPro LoadSearchResults JSON POST endpoint |
| 52 | **WeRecruit** | ATS | `werecruit` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public career portal HTML / JSON-LD |
| 53 | **Workable** | ATS | `workable` | **VERIFIED** | 1 | 100 | 100 | `5106492c` | https://apply.workable.com/credence | Public v3 Accounts Jobs JSON API (POST https://apply.workable.com/api/v3/accounts/{slug}/jobs + v2 detail) |
| 54 | **Workday** | ATS | `workday` | **VERIFIED** | 1 | 15 | 15 | `c822e084` | https://salesforce.wd12.myworkdayjobs.com/External_Career_Site | Workday Candidate Experience CXS JSON API (POST /wday/cxs/{tenant}/{site}/jobs + GET detail) |
| 55 | **Zoho Recruit** | ATS | `zoho_recruit` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Zoho Recruit Career Site JSON/RSS feed or HTML portal |
| 56 | **iCIMS** | ATS | `icims` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public iframe search mode (?in_iframe=1&pr={page}) + detail JobPosting JSON-LD |
| 57 | **iSolvedHire** | ATS | `isolvedhire` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML listing + RSS/JSON-LD extraction |
| 58 | **talentReef** | ATS | `talentreef` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | TalentReef public job board API / SPA portal |
| 59 | **Artha** | JOB_BOARD | `artha` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML / RSS feed + JSON-LD extraction |
| 60 | **CareerSiteCloud** | JOB_BOARD | `careersitecloud` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML listing + JSON-LD JobPosting |
| 61 | **JBoard.io** | JOB_BOARD | `jboard_io` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | JBoard Public HTML/RSS feed or REST API (requires operator API key for private API) |
| 62 | **JobBoard.com** | JOB_BOARD | `jobboard_com` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public RSS/XML feed or HTML + JSON-LD |
| 63 | **JobBoard.io** | JOB_BOARD | `jobboard_io` | **VERIFIED** | 1 | 20 | 20 | `33c68288` | https://www.cancercareers.org/jobs.rss | Official Public RSS 2.0 Job Feed ({board_origin}/jobs.rss) |
| 64 | **JobBoardFire** | JOB_BOARD | `jobboardfire` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML + JSON-LD extraction |
| 65 | **JobKit** | JOB_BOARD | `jobkit` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML / JSON-LD job listing extraction |
| 66 | **JobMount** | JOB_BOARD | `jobmount` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML / XML sitemap + JSON-LD extraction |
| 67 | **Jobboardly** | JOB_BOARD | `jobboardly` | **VERIFIED** | 1 | 8 | 8 | `850eaccb` | https://etcareers.com/ | Public /jobs/ index + detail schema.org JobPosting JSON-LD extraction |
| 68 | **Jobiqo** | JOB_BOARD | `jobiqo` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public RSS feed / Sitemap + schema.org JobPosting JSON-LD |
| 69 | **Niceboard** | JOB_BOARD | `niceboard` | **VERIFIED** | 1 | 17 | 17 | `af55af9c` | https://jobs.exitfive.com/ | Niceboard Public AJAX JSON API (GET /api/jobs with filter parameters & pagination) |
| 70 | **Nodex** | JOB_BOARD | `nodex` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML + schema.org JobPosting JSON-LD |
| 71 | **SmartJobBoard** | JOB_BOARD | `smartjobboard` | **VERIFIED** | 1 | 4 | 4 | `fd28b7bb` | https://master.mysmartjobboard.net/ | Public HTML listing (/job/{id}/{slug}/) + detail JobPosting JSON-LD & structured metadata extraction |
| 72 | **Talenetic** | JOB_BOARD | `talenetic` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public XML/RSS feed or HTML + JSON-LD extraction |
| 73 | **WP Job Manager** | JOB_BOARD | `wp_job_manager` | **VERIFIED** | 1 | 15 | 15 | `f2d961c1` | https://cycle-jobs.com/ | WordPress REST API v2 (/wp-json/wp/v2/job-listings) with fallback to /jm-ajax/get_listings and RSS job_feed |
| 74 | **Wiley Madgex** | JOB_BOARD | `wiley_madgex` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Madgex /jobsrss/ XML feed or paginated /jobs/ HTML + JSON-LD |
| 75 | **eJobBoard** | JOB_BOARD | `ejobboard` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML job board extraction |
| 76 | **ejobsitesoftware.com** | JOB_BOARD | `ejobsitesoftware_com` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public RSS/XML feed or HTML listing |
| 77 | **jobBoardHQ** | JOB_BOARD | `jobboardhq` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML / Atom feed extraction |
| 78 | **jobboardsoftware.com** | JOB_BOARD | `jobboardsoftware_com` | **NOT_IMPLEMENTED** | 0 | 0 | 0 | — | — | Public HTML listing + JSON-LD |
