
class Component extends DCLogic {
  jobs = [
    { id:'j1', mono:'A', grad:'linear-gradient(135deg,#1e3a8a,#2563eb)', title:'Senior Software Engineer', company:'Stripe', domain:'stripe.com', mode:'Remote', loc:'New York, NY', posted:'2d ago', source:'adzuna', isNew:true, score:87, skills:['Python','FastAPI','Distributed systems'], desc:"We're hiring a Senior Software Engineer to lead backend services powering our payments platform. You'll design distributed systems, mentor engineers, and own reliability for services handling millions of transactions per day.\n\nRequirements: 6+ years building production backends, strong Python, and experience operating high-scale systems." },
    { id:'j2', mono:'N', grad:'linear-gradient(135deg,#0f766e,#14b8a6)', title:'Backend Developer (Python)', company:'Airbnb', domain:'airbnb.com', mode:'On-site', loc:'Boston, MA', posted:'4d ago', source:'remotive', isNew:true, score:81, skills:['Python','PostgreSQL','REST APIs'], desc:"Northwind Labs is looking for a Backend Developer to build the APIs behind our analytics products. You'll work in Python and PostgreSQL, ship features end to end, and partner closely with our data team.\n\nNice to have: experience with async frameworks and cloud deployment." },
    { id:'j3', mono:'S', grad:'linear-gradient(135deg,#7c3aed,#a855f7)', title:'Platform Engineer', company:'Notion', domain:'notion.so', mode:'On-site', loc:'Hartford, CT', posted:'1d ago', source:'ctstatejobs', isNew:true, score:73, skills:['Kubernetes','CI/CD','Go'], desc:"Join the State of Connecticut's platform team to modernize infrastructure that citizens rely on. You'll manage Kubernetes clusters, build CI/CD pipelines, and improve reliability across services.\n\nThis is a stable, mission-driven role with strong benefits." },
    { id:'j4', mono:'B', grad:'linear-gradient(135deg,#b45309,#f59e0b)', title:'Staff Engineer', company:'Figma', domain:'figma.com', mode:'Remote', loc:'San Francisco, CA', posted:'3d ago', source:'greenhouse', isNew:false, score:79, skills:['System design','Python','Mentoring'], desc:"Brightwave is hiring a Staff Engineer to set technical direction across our core platform. You'll lead system design, raise the engineering bar, and mentor a growing team.\n\nWe value clear writing, pragmatic decisions, and a bias for shipping." },
    { id:'j5', mono:'H', grad:'linear-gradient(135deg,#be123c,#fb7185)', title:'Senior Backend Engineer', company:'Datadog', domain:'datadoghq.com', mode:'Remote', loc:'Austin, TX', posted:'5d ago', source:'lever', isNew:false, score:84, skills:['Python','FastAPI','AWS'], desc:"Helio Health builds software that helps clinics run smoothly. As a Senior Backend Engineer you'll design APIs in Python/FastAPI, deploy on AWS, and care deeply about correctness in a healthcare setting." },
    { id:'j6', mono:'C', grad:'linear-gradient(135deg,#1e40af,#3b82f6)', title:'API Engineer', company:'Plaid', domain:'plaid.com', mode:'Hybrid', loc:'Chicago, IL', posted:'1d ago', source:'adzuna', isNew:true, score:76, skills:['Java','Kafka','Microservices'], desc:"Cobalt Bank is modernizing its payments stack and needs an API Engineer to build resilient microservices. You'll work with Java and Kafka, define clean API contracts, and help retire legacy systems." }
  ];

  STAGES = ['Applied','Screening','Interview','Offer','Rejected'];

  // Per-job intel for the detail screen: company snapshot, key requirements, network, offer band.
  intel = {
    j1: { ind:'Fintech · Payments', size:'8,000+ employees', founded:'Founded 2010', funding:'Late stage · well funded', rating:4.3, reviews:'2.1k reviews', medianBase:'$192k median base',
          req:['Python','Distributed systems','AWS','Kubernetes','Go','Mentoring','PostgreSQL'],
          conns:[{n:'Priya Nair', r:'Staff Engineer · Payments', rel:'2nd · via Alex Chen', initial:'P'},{n:'Marcus Bell', r:'Engineering Manager', rel:'School alum', initial:'M'}],
          offer:{ base:'$195,000', equity:'$60k/yr equity', bonus:'15% target bonus', low:'$180k', high:'$235k' } },
    j2: { ind:'Travel · Marketplace', size:'6,000+ employees', founded:'Founded 2008', funding:'Public company', rating:4.1, reviews:'1.7k reviews', medianBase:'$176k median base',
          req:['Python','PostgreSQL','REST APIs','Async frameworks','AWS','Docker'],
          conns:[{n:'Dana Whitfield', r:'Senior Backend Engineer', rel:'2nd · via Sam Ortiz', initial:'D'}],
          offer:{ base:'$172,000', equity:'$40k/yr equity', bonus:'12% target bonus', low:'$160k', high:'$205k' } },
    j3: { ind:'Public sector · Infrastructure', size:'Government agency', founded:'State of Connecticut', funding:'Publicly funded', rating:3.9, reviews:'420 reviews', medianBase:'$128k median base',
          req:['Kubernetes','CI/CD','Go','Terraform','Linux','Networking'],
          conns:[], offer:{ base:'$125,000', equity:'Pension plan', bonus:'Step increases', low:'$115k', high:'$140k' } },
    j4: { ind:'Design · SaaS', size:'1,500+ employees', founded:'Founded 2012', funding:'Late stage · well funded', rating:4.5, reviews:'980 reviews', medianBase:'$230k median base',
          req:['System design','Python','Mentoring','Distributed systems','Leadership'],
          conns:[{n:'Renee Park', r:'Staff Engineer', rel:'1st · direct connection', initial:'R'},{n:'Ibrahim Khan', r:'Principal Engineer', rel:'2nd · via Renee Park', initial:'I'}],
          offer:{ base:'$235,000', equity:'$110k/yr equity', bonus:'18% target bonus', low:'$215k', high:'$290k' } },
    j5: { ind:'Developer tools · Observability', size:'5,000+ employees', founded:'Founded 2010', funding:'Public company', rating:4.2, reviews:'1.3k reviews', medianBase:'$188k median base',
          req:['Python','FastAPI','AWS','PostgreSQL','Observability','Microservices'],
          conns:[{n:'Tomas Reyes', r:'Engineering Manager', rel:'School alum', initial:'T'}],
          offer:{ base:'$190,000', equity:'$55k/yr equity', bonus:'15% target bonus', low:'$178k', high:'$225k' } },
    j6: { ind:'Fintech · Open banking', size:'1,200+ employees', founded:'Founded 2013', funding:'Late stage · well funded', rating:4.0, reviews:'610 reviews', medianBase:'$172k median base',
          req:['Java','Kafka','Microservices','REST APIs','Distributed systems'],
          conns:[{n:'Olivia Grant', r:'Senior API Engineer', rel:'2nd · via Priya Nair', initial:'O'}],
          offer:{ base:'$168,000', equity:'$45k/yr equity', bonus:'12% target bonus', low:'$155k', high:'$195k' } }
  };

  _reminderOf(stage){
    const map = {
      Applied:{ text:'Follow up in 3 days', bg:'#eef4ff', fg:'#2563eb' },
      Screening:{ text:'Recruiter call — prep notes', bg:'#eef4ff', fg:'#2563eb' },
      Interview:{ text:'Send a thank-you note', bg:'#fff4e6', fg:'#b45309' },
      Offer:{ text:'Review & negotiate your offer', bg:'#eaf7ee', fg:'#15803d' },
      Rejected:{ text:'Closed — archived', bg:'#f1f5f9', fg:'#64748b' }
    };
    return map[stage] || map.Applied;
  }

  suggData = [
    { txt:'Lead with your payments-platform migration to highlight distributed-systems work.', why:'This role emphasizes scale & reliability — your resume mentions both.' },
    { txt:'Surface your Python + FastAPI experience in your summary line.', why:'Listed as a core requirement for the role.' }
  ];

  scanSources = [
    { name:'adzuna', found:18 },
    { name:'remotive', found:9 },
    { name:'ctstatejobs', found:6 },
    { name:'greenhouse', found:11 },
    { name:'lever', found:4 },
    { name:'workday', found:7 }
  ];

  statesData = [
    { state:'Alabama', cities:['Birmingham','Montgomery','Mobile','Huntsville','Tuscaloosa','Auburn','Dothan','Hoover','Decatur','Madison'] },
    { state:'Alaska', cities:['Anchorage','Fairbanks','Juneau','Wasilla','Sitka','Ketchikan','Kenai','Kodiak'] },
    { state:'Arizona', cities:['Phoenix','Tucson','Mesa','Chandler','Scottsdale','Tempe','Gilbert','Glendale','Peoria','Flagstaff','Surprise','Yuma','Sedona'] },
    { state:'Arkansas', cities:['Little Rock','Fayetteville','Fort Smith','Springdale','Jonesboro','Bentonville','Conway','Rogers','Hot Springs'] },
    { state:'California', cities:['Los Angeles','San Francisco','San Diego','San Jose','Sacramento','Oakland','Fresno','Long Beach','Palo Alto','Mountain View','Sunnyvale','Santa Clara','Berkeley','Pasadena','Irvine','Santa Monica','Anaheim','Bakersfield','Riverside','Santa Barbara','Fremont','San Mateo','Cupertino','Menlo Park','Redwood City','Burbank','Glendale','Torrance','Carlsbad','Santa Cruz'] },
    { state:'Colorado', cities:['Denver','Boulder','Colorado Springs','Aurora','Fort Collins','Lakewood','Arvada','Westminster','Pueblo','Centennial','Littleton','Broomfield','Greeley','Longmont'] },
    { state:'Connecticut', cities:['Hartford','New Haven','Stamford','Bridgeport','Norwalk','Waterbury','Danbury','Greenwich','New Britain','West Hartford','Milford','Middletown'] },
    { state:'Delaware', cities:['Wilmington','Dover','Newark','Middletown','Bear','Smyrna','Milford','Rehoboth Beach'] },
    { state:'Florida', cities:['Miami','Orlando','Tampa','Jacksonville','Fort Lauderdale','St. Petersburg','Tallahassee','Gainesville','Sarasota','Naples','Boca Raton','West Palm Beach','Coral Gables','Hialeah','Clearwater','Pensacola','Fort Myers','Cape Coral','Kissimmee','Daytona Beach'] },
    { state:'Georgia', cities:['Atlanta','Savannah','Augusta','Athens','Columbus','Alpharetta','Macon','Roswell','Sandy Springs','Marietta','Decatur','Smyrna','Duluth','Johns Creek','Valdosta'] },
    { state:'Hawaii', cities:['Honolulu','Hilo','Kailua','Kapolei','Pearl City','Waipahu','Kaneohe','Lahaina','Kihei'] },
    { state:'Idaho', cities:['Boise','Meridian','Nampa','Idaho Falls','Pocatello','Caldwell','Coeur d\u2019Alene','Twin Falls'] },
    { state:'Illinois', cities:['Chicago','Aurora','Naperville','Springfield','Evanston','Schaumburg','Rockford','Joliet','Peoria','Elgin','Champaign','Bloomington','Oak Park','Skokie','Arlington Heights'] },
    { state:'Indiana', cities:['Indianapolis','Fort Wayne','Carmel','Bloomington','Evansville','South Bend','Fishers','Lafayette','Gary','Muncie','Noblesville'] },
    { state:'Iowa', cities:['Des Moines','Cedar Rapids','Iowa City','Davenport','Ames','West Des Moines','Sioux City','Waterloo','Council Bluffs','Ankeny'] },
    { state:'Kansas', cities:['Wichita','Kansas City','Overland Park','Olathe','Topeka','Lawrence','Manhattan','Lenexa','Shawnee'] },
    { state:'Kentucky', cities:['Louisville','Lexington','Bowling Green','Owensboro','Covington','Frankfort','Florence','Richmond'] },
    { state:'Louisiana', cities:['New Orleans','Baton Rouge','Shreveport','Lafayette','Lake Charles','Metairie','Bossier City','Monroe'] },
    { state:'Maine', cities:['Portland','Lewiston','Bangor','South Portland','Augusta','Biddeford','Brunswick','Saco'] },
    { state:'Maryland', cities:['Baltimore','Annapolis','Rockville','Bethesda','Frederick','Gaithersburg','Silver Spring','Columbia','Towson','Bowie','Germantown','College Park'] },
    { state:'Massachusetts', cities:['Boston','Cambridge','Worcester','Springfield','Lowell','Somerville','Newton','Quincy','Brookline','Framingham','Waltham','Medford','Lexington','Salem','Plymouth','Amherst'] },
    { state:'Michigan', cities:['Detroit','Ann Arbor','Grand Rapids','Lansing','Warren','Sterling Heights','Dearborn','Flint','Troy','Royal Oak','Kalamazoo','Novi','Livonia','Ypsilanti'] },
    { state:'Minnesota', cities:['Minneapolis','St. Paul','Rochester','Bloomington','Duluth','Plymouth','St. Cloud','Eden Prairie','Edina','Maple Grove','Eagan','Woodbury'] },
    { state:'Mississippi', cities:['Jackson','Gulfport','Southaven','Hattiesburg','Biloxi','Olive Branch','Tupelo','Meridian','Oxford'] },
    { state:'Missouri', cities:['Kansas City','St. Louis','Springfield','Columbia','Independence','Lee\u2019s Summit','O\u2019Fallon','St. Charles','St. Joseph','Joplin'] },
    { state:'Montana', cities:['Billings','Missoula','Bozeman','Great Falls','Helena','Kalispell','Butte','Whitefish'] },
    { state:'Nebraska', cities:['Omaha','Lincoln','Bellevue','Grand Island','Kearney','Fremont','Papillion'] },
    { state:'Nevada', cities:['Las Vegas','Reno','Henderson','North Las Vegas','Sparks','Carson City','Boulder City'] },
    { state:'New Hampshire', cities:['Manchester','Nashua','Concord','Dover','Portsmouth','Rochester','Keene','Hanover'] },
    { state:'New Jersey', cities:['Newark','Jersey City','Hoboken','Princeton','Trenton','Edison','Paterson','Elizabeth','Hackensack','Montclair','Morristown','New Brunswick','Camden','Atlantic City','Paramus','Cherry Hill'] },
    { state:'New Mexico', cities:['Albuquerque','Santa Fe','Las Cruces','Rio Rancho','Roswell','Farmington','Taos'] },
    { state:'New York', cities:['New York City','Manhattan','Brooklyn','Queens','Bronx','Staten Island','Buffalo','Rochester','Yonkers','Syracuse','Albany','New Rochelle','Mount Vernon','Schenectady','Utica','White Plains','Troy','Niagara Falls','Binghamton','Ithaca','Poughkeepsie','Long Island City','Astoria','Flushing','Jamaica','Hempstead','Levittown','Huntington','Smithtown','St. Charles','Stony Brook','Setauket','Port Jefferson','Patchogue','Riverhead','Babylon','Islip','Brentwood','Commack','Hauppauge','Ronkonkoma','Sayville','Bay Shore','Massapequa','Hicksville','Garden City','Mineola','Great Neck','Glen Cove','Freeport','Long Beach','Rockville Centre','Farmingdale','Bethpage','Plainview','Syosset','Oyster Bay','Westbury','New Hyde Park','Valley Stream','Lindenhurst','Amityville','East Hampton','Southampton','Montauk','Saratoga Springs','Kingston','Newburgh','Middletown','Nyack','Tarrytown','Scarsdale','Rye','Mamaroneck','Ossining','Peekskill','Cortlandt','Yorktown','Suffern','Spring Valley','Nanuet'] },
    { state:'North Carolina', cities:['Charlotte','Raleigh','Durham','Greensboro','Asheville','Cary','Winston-Salem','Fayetteville','Wilmington','Chapel Hill','High Point','Concord','Greenville','Apex'] },
    { state:'North Dakota', cities:['Fargo','Bismarck','Grand Forks','Minot','West Fargo','Mandan','Dickinson'] },
    { state:'Ohio', cities:['Columbus','Cleveland','Cincinnati','Toledo','Akron','Dayton','Dublin','Westerville','Canton','Youngstown','Hilliard','Beavercreek'] },
    { state:'Oklahoma', cities:['Oklahoma City','Tulsa','Norman','Edmond','Broken Arrow','Lawton','Stillwater','Moore'] },
    { state:'Oregon', cities:['Portland','Eugene','Salem','Bend','Beaverton','Hillsboro','Gresham','Medford','Corvallis','Tigard','Lake Oswego','Ashland'] },
    { state:'Pennsylvania', cities:['Philadelphia','Pittsburgh','Allentown','Erie','Harrisburg','Bethlehem','Lancaster','Scranton','Reading','State College','King of Prussia','West Chester','Doylestown'] },
    { state:'Rhode Island', cities:['Providence','Warwick','Cranston','Pawtucket','Newport','East Providence','Woonsocket'] },
    { state:'South Carolina', cities:['Charleston','Columbia','Greenville','Mount Pleasant','Rock Hill','Spartanburg','Myrtle Beach','Hilton Head Island','Summerville'] },
    { state:'South Dakota', cities:['Sioux Falls','Rapid City','Aberdeen','Brookings','Watertown','Pierre'] },
    { state:'Tennessee', cities:['Nashville','Memphis','Knoxville','Chattanooga','Franklin','Murfreesboro','Clarksville','Brentwood','Germantown'] },
    { state:'Texas', cities:['Austin','Houston','Dallas','San Antonio','Fort Worth','El Paso','Plano','Arlington','Frisco','Irving','McKinney','Round Rock','Corpus Christi','Lubbock','Laredo','Garland','Denton','Sugar Land','The Woodlands','Allen','Richardson','Waco','College Station','Galveston'] },
    { state:'Utah', cities:['Salt Lake City','Provo','Lehi','Park City','Ogden','Sandy','West Valley City','Orem','St. George','Draper','American Fork'] },
    { state:'Vermont', cities:['Burlington','South Burlington','Montpelier','Rutland','Essex','Stowe','Brattleboro'] },
    { state:'Virginia', cities:['Arlington','Richmond','Alexandria','Virginia Beach','Reston','Norfolk','Chesapeake','Charlottesville','Fairfax','McLean','Vienna','Herndon','Roanoke','Blacksburg','Leesburg','Ashburn'] },
    { state:'Washington', cities:['Seattle','Spokane','Tacoma','Bellevue','Redmond','Kirkland','Everett','Renton','Bellingham','Olympia','Vancouver','Kent','Sammamish','Issaquah','Bothell'] },
    { state:'West Virginia', cities:['Charleston','Huntington','Morgantown','Parkersburg','Wheeling','Martinsburg','Beckley'] },
    { state:'Wisconsin', cities:['Milwaukee','Madison','Green Bay','Kenosha','Racine','Appleton','Waukesha','Eau Claire','Oshkosh','Janesville'] },
    { state:'Wyoming', cities:['Cheyenne','Casper','Laramie','Gillette','Jackson','Sheridan','Rock Springs'] },
    { state:'Washington, D.C.', cities:['Washington'] }
  ];

  countriesData = [
    { country:'United States', regionLabel:'State', regions: this.statesData },
    { country:'Canada', regionLabel:'Province', regions:[
      { state:'Ontario', cities:['Toronto','Ottawa','Mississauga','Hamilton','London','Markham','Vaughan','Kitchener','Waterloo','Windsor','Brampton','Burlington','Oakville'] },
      { state:'Quebec', cities:['Montreal','Quebec City','Laval','Gatineau','Sherbrooke','Longueuil','Trois-Rivières'] },
      { state:'British Columbia', cities:['Vancouver','Victoria','Surrey','Burnaby','Richmond','Kelowna','Coquitlam','Nanaimo'] },
      { state:'Alberta', cities:['Calgary','Edmonton','Red Deer','Lethbridge','Banff'] },
      { state:'Manitoba', cities:['Winnipeg','Brandon'] },
      { state:'Saskatchewan', cities:['Saskatoon','Regina'] },
      { state:'Nova Scotia', cities:['Halifax','Dartmouth','Sydney'] },
      { state:'New Brunswick', cities:['Moncton','Fredericton','Saint John'] }
    ] },
    { country:'United Kingdom', regionLabel:'County / Region', regions:[
      { state:'Greater London', cities:['London','Croydon','Bromley','Ealing','Wembley','Richmond','Greenwich'] },
      { state:'Greater Manchester', cities:['Manchester','Salford','Bolton','Stockport','Oldham'] },
      { state:'West Midlands', cities:['Birmingham','Coventry','Wolverhampton','Solihull'] },
      { state:'Merseyside', cities:['Liverpool','Birkenhead','St Helens'] },
      { state:'West Yorkshire', cities:['Leeds','Bradford','Wakefield','Huddersfield'] },
      { state:'Scotland', cities:['Edinburgh','Glasgow','Aberdeen','Dundee','Stirling'] },
      { state:'Wales', cities:['Cardiff','Swansea','Newport','Wrexham'] },
      { state:'Northern Ireland', cities:['Belfast','Derry','Lisburn'] },
      { state:'Bristol', cities:['Bristol','Bath'] },
      { state:'Cambridgeshire', cities:['Cambridge','Peterborough'] }
    ] },
    { country:'Ireland', regionLabel:'County', regions:[
      { state:'Dublin', cities:['Dublin','Swords','Tallaght','Dún Laoghaire'] },
      { state:'Cork', cities:['Cork','Cobh'] },
      { state:'Galway', cities:['Galway'] },
      { state:'Limerick', cities:['Limerick'] }
    ] },
    { country:'Australia', regionLabel:'State / Territory', regions:[
      { state:'New South Wales', cities:['Sydney','Newcastle','Wollongong','Parramatta'] },
      { state:'Victoria', cities:['Melbourne','Geelong','Ballarat','Bendigo'] },
      { state:'Queensland', cities:['Brisbane','Gold Coast','Cairns','Townsville'] },
      { state:'Western Australia', cities:['Perth','Fremantle','Mandurah'] },
      { state:'South Australia', cities:['Adelaide'] },
      { state:'Australian Capital Territory', cities:['Canberra'] },
      { state:'Tasmania', cities:['Hobart','Launceston'] }
    ] },
    { country:'Germany', regionLabel:'State', regions:[
      { state:'Berlin', cities:['Berlin'] },
      { state:'Bavaria', cities:['Munich','Nuremberg','Augsburg','Würzburg'] },
      { state:'Hesse', cities:['Frankfurt','Wiesbaden','Darmstadt'] },
      { state:'Hamburg', cities:['Hamburg'] },
      { state:'North Rhine-Westphalia', cities:['Cologne','Düsseldorf','Dortmund','Bonn','Essen'] },
      { state:'Baden-Württemberg', cities:['Stuttgart','Karlsruhe','Mannheim','Heidelberg'] }
    ] },
    { country:'France', regionLabel:'Region', regions:[
      { state:'Île-de-France', cities:['Paris','Versailles','Boulogne-Billancourt'] },
      { state:'Auvergne-Rhône-Alpes', cities:['Lyon','Grenoble','Saint-Étienne'] },
      { state:'Provence-Alpes-Côte d\u2019Azur', cities:['Marseille','Nice','Cannes','Aix-en-Provence'] },
      { state:'Occitanie', cities:['Toulouse','Montpellier'] },
      { state:'Nouvelle-Aquitaine', cities:['Bordeaux'] }
    ] },
    { country:'Netherlands', regionLabel:'Province', regions:[
      { state:'North Holland', cities:['Amsterdam','Haarlem'] },
      { state:'South Holland', cities:['Rotterdam','The Hague','Leiden','Delft'] },
      { state:'Utrecht', cities:['Utrecht','Amersfoort'] },
      { state:'North Brabant', cities:['Eindhoven','Tilburg'] }
    ] },
    { country:'India', regionLabel:'State', regions:[
      { state:'Maharashtra', cities:['Mumbai','Pune','Nagpur','Nashik'] },
      { state:'Karnataka', cities:['Bengaluru','Mysuru','Mangaluru'] },
      { state:'Delhi (NCT)', cities:['New Delhi','Delhi','Noida','Gurugram'] },
      { state:'Telangana', cities:['Hyderabad'] },
      { state:'Tamil Nadu', cities:['Chennai','Coimbatore'] },
      { state:'West Bengal', cities:['Kolkata'] }
    ] },
    { country:'Singapore', regionLabel:'Region', regions:[
      { state:'Central', cities:['Singapore'] }
    ] },
    { country:'Other (worldwide)', regionLabel:'Region', regions:[] }
  ];

  suggestGroups = [
    { label:'Software Engineering', words:['python','javascript','typescript','react','node.js','go','java','aws','kubernetes','sql','backend','frontend','devops'] },
    { label:'Data & AI', words:['data analysis','machine learning','pandas','nlp','data engineering','analytics','tableau','etl'] },
    { label:'Product & Design', words:['product management','ux design','ui design','figma','user research','roadmap','prototyping'] },
    { label:'Marketing & Growth', words:['seo','content marketing','growth','social media','copywriting','email marketing'] },
    { label:'Seniority & type', words:['senior','staff','lead','manager','entry-level','internship','contract','remote'] }
  ];

  salaryById = { j1:'$160–200k', j2:'$130–160k', j3:'$110–140k', j4:'$190–240k', j5:'$150–185k', j6:'$140–175k' };

  sourceMeta = {
    adzuna:{ label:'Adzuna', url:'https://www.adzuna.com' },
    remotive:{ label:'Remotive', url:'https://remotive.com' },
    ctstatejobs:{ label:'CT State Jobs', url:'https://www.jobapscloud.com/CT' },
    greenhouse:{ label:'Greenhouse', url:'https://boards.greenhouse.io' },
    lever:{ label:'Lever', url:'https://jobs.lever.co' },
    workday:{ label:'Workday', url:'https://www.workday.com' }
  };

  resumeData = {
    name:'Jordan Lee',
    title:'Senior Backend Engineer',
    contact:'jordan.lee@email.com · San Francisco, CA · linkedin.com/in/jordanlee',
    summary:'Backend engineer with 7+ years building reliable, high-scale services in Python. Led payments-platform work handling millions of transactions a day.',
    experience:[
      { role:'Senior Backend Engineer', company:'Loop Payments', dates:'2021 — Present', bullets:['Led migration of the payments platform to a distributed, event-driven architecture.','Cut p99 latency 38% and lifted reliability to 99.99%.'] },
      { role:'Backend Engineer', company:'Northwind Labs', dates:'2018 — 2021', bullets:['Built Python/FastAPI services powering analytics for 200+ clients.','Mentored 4 engineers and owned the on-call rotation.'] }
    ],
    skills:['Python','FastAPI','PostgreSQL','AWS','Kubernetes','Distributed systems','CI/CD']
  };
  builderTemplates = [
    { id:'modern', name:'Modern', tag:'Accent header · single column' },
    { id:'classic', name:'Classic', tag:'ATS-safe · clean lines' },
    { id:'twocol', name:'Two-column', tag:'Sidebar + main' },
    { id:'minimal', name:'Minimal', tag:'Lots of whitespace' }
  ];

  state = {
    screen:'splash', tab:'foryou', jobId:null, authMode:'signin', authStep:'entry', authContact:'', authPhone:'', twoFactor:false, authError:false, authErrorField:null, booting:false, onboarding:false, onbStep:0,
    starred:{ j1:true }, applied:{ j6:true }, refused:[], stages:{ j6:'Interview' }, pipeFilter:'All',
    reviewDeck:[], reviewIdx:0, insightWeek:0,
    editProfile:false, profilePic:null,
    profile:{ name:'Jordan Lee', email:'you@example.com', phone:'', location:'New York, NY', headline:'Senior Backend Engineer' },
    resumes:[
      { id:'r1', name:'Jordan_Lee_Resume.pdf', type:'PDF', meta:'Uploaded Jun 22 · used for all matches', def:true, detected:['python','fastapi','backend','aws','sql','distributed systems','postgresql','devops'] },
      { id:'r2', name:'Jordan_Lee_PM.docx', type:'DOCX', meta:'Uploaded Jun 10', def:false, detected:['product management','roadmap','user research','analytics','figma'] }
    ],
    scanning:false, scanStage:0, flash:null,
    dragHome:false, dragRes:false,
    suggSel:{0:true,1:true}, appliedEdits:false,
    drafting:false, draft:'',
    keywords:['python','fastapi','backend'], workType:'Remote',
    loc:{ country:'United States', region:'', city:'', radius:'25 miles' }, locOpen:null, locQuery:'', suggestOpen:true,
    expLevels:[], jobTypes:[], datePosted:'Any time', companySizes:[], industries:[],
    easyApply:false, sponsorship:false, excludeAgencies:false,
    minSalary:'$120,000', alertMode:'top',
    theme:'dark', prodUpdates:true, weeklyEmail:true, jobAlertEmail:true,
    alertChannels:{ email:true, push:true, sms:false },
    excludeKeywords:['contract'], excludeDraft:'', blockedCompanies:[], blockDraft:'', minRating:'Any',
    builderTemplate:'modern', builderPhase:'idle'
  };

  showFlash = (type,msg) => { this.setState({flash:{type,msg}}); clearTimeout(this._ft); this._ft = setTimeout(()=>this.setState({flash:null}), 3600); };
  signIn = () => this.setState({screen:'home', onboarding:true, onbStep:0});
  onbNext = () => this.setState(st => (st.onbStep >= 2 ? { onboarding:false } : { onbStep: st.onbStep + 1 }));
  onbBack = () => this.setState(st => ({ onbStep: Math.max(0, st.onbStep - 1) }));
  onbSkip = () => this.setState({ onboarding:false });
  startBoot = () => { this.setState({ booting:true }); clearTimeout(this._boot); this._boot = setTimeout(() => this.setState({ screen:'login', booting:false }), 1500); };
  setAuth = (m) => () => this.setState({ authMode:m, authStep:'entry', authError:false });
  onAuthContact = (e) => this.setState({ authContact: e.target.value, authError:false });
  onAuthPhone = (e) => this.setState({ authPhone: e.target.value, authError:false });
  toggleTwoFactor = () => this.setState(st => ({ twoFactor: !st.twoFactor, authError:false }));
  _validEmail(v){ return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test((v||'').trim()); }
  _validPhone(v){ const d=(v||'').replace(/[^0-9]/g,''); return /^\+?[0-9().\-\s]+$/.test((v||'').trim()) && d.length>=10 && d.length<=15; }
  sendCode = () => { this.signIn(); }; // TEMP: skip code step for building
  verifyEmailCode = () => { if (this.state.twoFactor) { this.setState({ authStep:'code2' }); this.showFlash('success','Code texted to your phone.'); } else { this.signIn(); } };
  resendCode = () => this.showFlash('success','New code sent.');
  backToEntry = () => this.setState({ authStep:'entry' });
  backToCode = () => this.setState({ authStep:'code' });
  onCodeInput = (e) => { const el = e.target; el.value = el.value.replace(/[^0-9]/g,'').slice(0,1); const nx = el.nextElementSibling; if (el.value && nx && nx.tagName==='INPUT') nx.focus(); };
  onCodeKey = (e) => { const el = e.target; if (e.key==='Backspace' && !el.value) { const pv = el.previousElementSibling; if (pv && pv.tagName==='INPUT') pv.focus(); } };
  go = (s) => () => this.setState({screen:s, jobId:null});
  setTab = (t) => () => this.setState({tab:t});
  toggleStar = (id) => { this.setState(st => { const s = {...st.starred}; if (s[id]) delete s[id]; else s[id]=true; return {starred:s}; }); };
  dismissJob = (id) => (e) => { if (e) e.stopPropagation(); this.setState(st => ({refused:[id, ...st.refused.filter(x => x!==id)]})); this.showFlash('info','Removed from your queue.'); };
  restoreJob = (id) => { this.setState(st => ({refused: st.refused.filter(x => x!==id)})); this.showFlash('success','Restored to your queue.'); };
  notInterested = () => { const id = this.state.jobId; this.setState(st => ({ refused:[id, ...st.refused.filter(x => x!==id)], screen:'dashboard', tab:'foryou' })); this.showFlash('info','Marked not interested — we won\u2019t show it again.'); };
  openJob = (id) => this.setState({screen:'job', jobId:id, appliedEdits:false, drafting:false, draft:'', suggSel:{0:true,1:true}});
  back = () => this.setState({screen:'dashboard'});
  markApplied = () => { const id = this.state.jobId; this.setState(st => ({ applied:{...st.applied,[id]:true}, stages:{...st.stages, [id]: st.stages[id] || 'Applied'}, screen:'dashboard', tab:'applied' })); this.showFlash('success','✓ Application marked as sent.'); };
  selectTemplate = (id) => () => this.setState({builderTemplate:id, builderPhase:'idle'});
  reformat = () => { if (this.state.builderPhase==='working') return; this.setState({builderPhase:'working'}); clearTimeout(this._bt); this._bt = setTimeout(() => this.setState({builderPhase:'done'}), 1800); };
  saveBuilt = () => this.showFlash('success','✓ Reformatted resume saved to your resumes.');
  onLogoError = (e) => { e.target.style.display='none'; const m = e.target.nextSibling; if (m) m.style.display='grid'; };
  _fileToName(fn){ if(!fn) return this.props.userName || 'Jordan Lee'; const base = fn.replace(/\.[a-z0-9]+$/i,'').replace(/[_\-]+/g,' '); const stop={resume:1,cv:1,final:1,copy:1,updated:1,v2:1}; const parts = base.split(' ').filter(w => w && !stop[w.toLowerCase()] && !/^\d+$/.test(w)); const np = parts.slice(0,2); return np.length ? np.join(' ') : (this.props.userName || 'Jordan Lee'); }
  refresh = () => {
    if (this.state.scanning) return;
    const total = this.scanSources.length;
    this.setState({scanning:true, scanStage:0});
    clearInterval(this._scan);
    this._scan = setInterval(() => {
      this.setState(st => {
        if (st.scanStage >= total) { clearInterval(this._scan); return null; }
        return {scanStage: st.scanStage + 1};
      });
    }, 540);
    clearTimeout(this._st);
    this._st = setTimeout(() => { clearInterval(this._scan); this.setState({scanning:false}); this.showFlash('success','✓ Scan complete — 6 new matches found.'); }, total*540 + 900);
  };

  addResume = (file) => { const name = file && file.name ? file.name : 'Resume.pdf'; const type = /\.docx?$/i.test(name) ? 'DOCX' : 'PDF'; const detected = ['python','javascript','sql','aws','react','communication']; this.setState(st => { const def = st.resumes.length===0; const kw = def ? [...st.keywords, ...detected.filter(d => st.keywords.indexOf(d)<0)] : st.keywords; return { resumes:[...st.resumes, {id:'r'+Date.now(), name, type, meta:'Just now', def, detected}], keywords:kw, dragHome:false, dragRes:false }; }); this.showFlash('success','✓ '+name+' uploaded — skills added to your preferences.'); };
  onDropHome = (e) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; this.addResume(f); };
  onDropRes = (e) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; this.addResume(f); };
  dragHomeOn = (e) => { e.preventDefault(); e.stopPropagation(); if (!this.state.dragHome) this.setState({dragHome:true}); };
  dragHomeOff = (e) => { e.preventDefault(); e.stopPropagation(); this.setState({dragHome:false}); };
  dragResOn = (e) => { e.preventDefault(); e.stopPropagation(); if (!this.state.dragRes) this.setState({dragRes:true}); };
  dragResOff = (e) => { e.preventDefault(); e.stopPropagation(); this.setState({dragRes:false}); };
  onPickHome = (e) => { const f = e.target.files && e.target.files[0]; if (f) this.addResume(f); };
  onPickRes = (e) => { const f = e.target.files && e.target.files[0]; if (f) this.addResume(f); };
  toggleSugg = (i) => this.setState(st => { const s = {...st.suggSel}; s[i] = !s[i]; return {suggSel:s}; });
  applyEdits = () => { const n = Object.values(this.state.suggSel).filter(Boolean).length; this.setState({appliedEdits:true}); this.showFlash('success','✓ Resume tailored — '+n+' edit'+(n===1?'':'s')+' applied.'); };
  openCombo = (which) => (e) => { if (e) e.stopPropagation(); this.setState({locOpen:which, locQuery:''}); };
  closeCombo = (e) => { if (e) e.stopPropagation(); this.setState({locOpen:null, locQuery:''}); };
  onLocType = (e) => this.setState({locQuery:e.target.value});
  pickCountry = (name) => this.setState(st => ({ loc:{...st.loc, country:name, region:'', city:''}, locOpen:null, locQuery:'' }));
  pickRegion = (name) => this.setState(st => ({ loc:{...st.loc, region:name, city:''}, locOpen:null, locQuery:'' }));
  pickCity = (name) => this.setState(st => ({ loc:{...st.loc, city:name}, locOpen:null, locQuery:'' }));
  pickRadius = (r) => this.setState(st => ({ loc:{...st.loc, radius:r}, locOpen:null, locQuery:'' }));
  toggleSuggest = () => this.setState(st => ({ suggestOpen: !st.suggestOpen }));
  setStage = (id, stage) => this.setState(st => ({ stages:{...st.stages, [id]:stage} }));
  onStageSelect = (id) => (e) => this.setStage(id, e.target.value);
  setPipeFilter = (f) => () => this.setState({ pipeFilter:f });
  goTab = (t) => () => this.setState({ screen:'dashboard', tab:t });
  openEditProfile = () => this.setState({ editProfile:true });
  closeEditProfile = () => this.setState({ editProfile:false });
  saveProfile = () => { this.setState({ editProfile:false }); this.showFlash('success','✓ Profile updated.'); };
  onProfileField = (key) => (e) => { const v = e.target.value; this.setState(st => ({ profile:{...st.profile, [key]:v} })); };
  onProfilePic = (e) => { const f = e.target.files && e.target.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = (ev) => this.setState({ profilePic: ev.target.result }); rd.readAsDataURL(f); };
  removeProfilePic = () => this.setState({ profilePic:null });
  onWeekSelect = (e) => this.setState({ insightWeek: parseInt(e.target.value,10) });
  weekPrev = () => this.setState(st => ({ insightWeek: Math.min(3, st.insightWeek + 1) }));
  weekNext = () => this.setState(st => ({ insightWeek: Math.max(0, st.insightWeek - 1) }));
  onMinSalary = (e) => this.setState({ minSalary: e.target.value });
  onAlertMode = (e) => this.setState({ alertMode: e.target.value });
  toggleChannel = (ch) => () => this.setState(st => ({ alertChannels:{...st.alertChannels, [ch]: !st.alertChannels[ch]} }));
  onExcludeDraft = (e) => this.setState({ excludeDraft: e.target.value });
  addExclude = (e) => { if (e.key !== 'Enter') return; e.preventDefault(); const v = (this.state.excludeDraft||'').trim(); if (!v) return; this.setState(st => ({ excludeKeywords: st.excludeKeywords.indexOf(v)>=0 ? st.excludeKeywords : [...st.excludeKeywords, v], excludeDraft:'' })); };
  removeExclude = (kw) => () => this.setState(st => ({ excludeKeywords: st.excludeKeywords.filter(x => x!==kw) }));
  onBlockDraft = (e) => this.setState({ blockDraft: e.target.value });
  addBlock = (e) => { if (e.key !== 'Enter') return; e.preventDefault(); const v = (this.state.blockDraft||'').trim(); if (!v) return; this.setState(st => ({ blockedCompanies: st.blockedCompanies.indexOf(v)>=0 ? st.blockedCompanies : [...st.blockedCompanies, v], blockDraft:'' })); };
  removeBlock = (c) => () => this.setState(st => ({ blockedCompanies: st.blockedCompanies.filter(x => x!==c) }));
  onMinRating = (e) => this.setState({ minRating: e.target.value });
  enterReview = () => { const refused = this.state.refused; const deck = this.jobs.filter(j => refused.indexOf(j.id) < 0).sort((a,b)=>b.score-a.score).map(j=>j.id); this.setState({ screen:'review', reviewDeck:deck, reviewIdx:0 }); };
  exitReview = () => this.setState({ screen:'dashboard', tab:'foryou' });
  _reviewId(){ return (this.state.reviewDeck||[])[this.state.reviewIdx]; }
  reviewKeep = () => { const id = this._reviewId(); if(!id) return; this.setState(st => ({ starred:{...st.starred,[id]:true}, reviewIdx: st.reviewIdx+1 })); this.showFlash('success','★ Saved to your list.'); };
  reviewSkip = () => { const id = this._reviewId(); if(!id) return; this.setState(st => ({ refused:[id, ...st.refused.filter(x=>x!==id)], reviewIdx: st.reviewIdx+1 })); };
  reviewApplyStep = () => { const id = this._reviewId(); if(!id) return; this.setState(st => ({ applied:{...st.applied,[id]:true}, stages:{...st.stages,[id]: st.stages[id]||'Applied'}, reviewIdx: st.reviewIdx+1 })); this.showFlash('success','✓ Marked as applied.'); };
  reviewOpen = () => { const id = this._reviewId(); if(id) this.openJob(id); };
  draftAnswer = () => { if (this.state.drafting) return; this.setState({drafting:true}); const job = this._current(); clearTimeout(this._dt); this._dt = setTimeout(()=>{ this.setState({drafting:false, draft:this._draftText(job)}); }, 1600); };
  onDraftInput = (e) => this.setState({draft:e.target.value});
  setWorkType = (w) => () => this.setState({workType:w});
  toggleIn = (key, val) => () => this.setState(s => { const arr = s[key]; return { [key]: arr.indexOf(val) >= 0 ? arr.filter(x => x !== val) : [...arr, val] }; });
  setDatePosted = (v) => () => this.setState({datePosted:v});
  toggleBool = (key) => () => this.setState(s => ({ [key]: !s[key] }));
  savePrefs = () => this.showFlash('success','✓ Preferences saved — applies on your next refresh.');
  setTheme = (t) => () => this.setState({ theme:t });
  saveOptions = () => this.showFlash('success','✓ Settings saved.');
  deleteAccount = () => this.showFlash('info','Account deletion is disabled in this demo.');

  _current(){ return this.jobs.find(j => j.id===this.state.jobId) || this.jobs[0]; }
  _draftText(job){ return "I'm genuinely excited about "+job.company+"'s work — the "+job.title+" role lines up closely with what I love building. In my last position I led "+job.skills[0]+" and "+job.skills[1]+" projects end to end, and I'd bring that same ownership here. What draws me most is the chance to do this at scale while staying close to the people the product serves."; }
  _tabStyle(active){ return {padding:'0 0 12px',fontWeight:600,fontSize:'14px',cursor:'pointer',fontFamily:"'Space Grotesk',sans-serif",color:active?'#0f1730':'#8294b5',borderBottom:active?'2px solid #2563eb':'2px solid transparent'}; }
  _zone(drag){ return {display:'block',cursor:'pointer',borderRadius:'16px',padding:'34px',textAlign:'center',border:'2px dashed '+(drag?'#2563eb':'#b9cdf2'),background:drag?'#e7f0ff':'linear-gradient(180deg,#eef4ff,#ffffff)',transition:'border-color .15s, background .15s'}; }
  _applyStyle(applied){ return {display:'inline-flex',alignItems:'center',gap:'7px',background:applied?'#dcfce7':'#0f1730',color:applied?'#15803d':'#fff',border:0,padding:'10px 16px',borderRadius:'11px',fontWeight:600,fontSize:'14px',cursor:'pointer',fontFamily:"'Space Grotesk',sans-serif"}; }
  _flashStyle(flash){ const t = flash?flash.type:'success'; const map = {success:['#ecfdf3','#15803d','#bbf7d0'],info:['#eff6ff','#1e40af','#bfdbfe'],error:['#fef2f2','#b91c1c','#fecaca']}; const c = map[t]||map.success; return {position:'fixed',top:'20px',left:'50%',transform:'translate(-50%,0)',zIndex:50,background:c[0],color:c[1],border:'1px solid '+c[2],padding:'12px 18px',borderRadius:'12px',fontWeight:600,fontSize:'14px',boxShadow:'0 12px 30px -12px rgba(16,24,40,.25)',animation:'jbfade .25s ease'}; }

  renderVals(){
    const st = this.state;
    const name = (st.profile.name || this.props.userName || 'Jordan');
    const first = name.split(' ')[0];
    const h = new Date().getHours();
    const part = h < 12 ? 'Morning' : h < 18 ? 'Afternoon' : 'Evening';
    const scoreStyle = this.props.scoreStyle || 'skills';
    const showRing = scoreStyle === 'ring';
    const starred = st.starred;
    const applied = st.applied;
    const navItem = (active) => ({display:'flex',alignItems:'center',gap:'11px',padding:'10px 12px',borderRadius:'10px',fontWeight:600,fontSize:'14px',cursor:'pointer',background:active?'rgba(122,162,255,.16)':'transparent',color:active?'#fff':'#9fb0cf'});
    const seg = (active) => ({padding:'8px 16px',borderRadius:'8px',fontWeight:600,fontSize:'13px',cursor:'pointer',fontFamily:"'Space Grotesk',sans-serif",background:active?'#0f1730':'transparent',color:active?'#fff':'#64748b'});
    const onMatches = st.screen==='dashboard' || st.screen==='job';
    const pad = (n) => (n<10?'0':'')+n;
    const fitOf = (s) => s>=85 ? {label:'Excellent fit',green:true} : s>=78 ? {label:'Strong fit',green:true} : {label:'Good fit',green:false};
    const dark = (st.theme==='dark' || (st.theme==='system' && typeof window!=='undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches));
    const logoTints = ['#38BDF8','#ED93B1','#5DCAA5','#EF9F27','#AFA9EC'];
    const tintFor = (j) => logoTints[Math.max(0,this.jobs.indexOf(j)) % logoTints.length];
    const logoTile = {width:'44px',height:'44px',flex:'none',borderRadius:'12px',background: dark?'#1E2D45':'#fff',border:'1px solid '+(dark?'#1E2D45':'#e6ecf6'),display:'grid',placeItems:'center',boxShadow:'0 3px 8px -3px rgba(15,23,48,.18)'};
    const notch = {width:'8px',height:'8px',background:'#fff',borderRadius:'2px'};
    const markBg = (j) => dark ? tintFor(j) : j.grad;
    const rowView = (j, rank) => { const fit = fitOf(j.score); return {
      id:j.id, title:j.title, isNew:!!j.isNew, rank: rank,
      companyLine: j.company+' · '+j.mode+' · '+j.loc,
      salary: this.salaryById[j.id],
      logoTileStyle: logoTile,
      logoSrc: 'https://logo.clearbit.com/'+j.domain,
      logoMarkStyle: {width:'23px',height:'23px',borderRadius:'7px',background:markBg(j),display:'grid',placeItems:'center'},
      logoMarkHidden: {width:'23px',height:'23px',borderRadius:'7px',background:markBg(j),display:'none',placeItems:'center'},
      logoNotchStyle: notch,
      fitLabel: fit.label,
      fitStyle: fit.green ? {background:'#eaf7ee',color:'#15803d',border:'1px solid #bfe6cb',borderRadius:'7px',padding:'2px 9px',fontSize:'12px',fontWeight:600,whiteSpace:'nowrap'} : {background:'#eaf1ff',color:'#2563eb',border:'1px solid #cfe0ff',borderRadius:'7px',padding:'2px 9px',fontSize:'12px',fontWeight:600,whiteSpace:'nowrap'},
      isApplied: !!applied[j.id],
      starChar: starred[j.id]?'★':'☆',
      starStyle: {fontSize:'19px',color:starred[j.id]?'#f59e0b':'#cbd5e1',cursor:'pointer',background:'none',border:0,padding:0,lineHeight:1,flex:'none'},
      onOpen: () => this.openJob(j.id),
      onStar: (e) => { e.stopPropagation(); this.toggleStar(j.id); },
      onDismiss: this.dismissJob(j.id)
    }; };
    // Queue ranking: favorited first, then applied, then by fit score.
    const priorityOf = (j) => { let p = j.score; if (applied[j.id]) p += 1000; if (starred[j.id]) p += 2000; return p; };
    const ranked = this.jobs.filter(j => st.refused.indexOf(j.id) < 0).sort((a,b) => priorityOf(b) - priorityOf(a));
    const featuredJob = ranked[0] || this.jobs[0];
    const fStar = !!starred[featuredJob.id];
    const fFit = fitOf(featuredJob.score);
    const featured = {
      title: featuredJob.title,
      fitLabel: fFit.label,
      sub: featuredJob.company+' · '+featuredJob.mode+' · '+featuredJob.loc,
      why: 'Strongest match this week — your '+featuredJob.skills[0]+', '+featuredJob.skills[1]+' and '+featuredJob.skills[2]+' experience line up with the core requirements.',
      logoSrc: 'https://logo.clearbit.com/'+featuredJob.domain,
      logoMarkStyle: {width:'24px',height:'24px',borderRadius:'7px',background:featuredJob.grad,display:'grid',placeItems:'center'},
      logoMarkHidden: {width:'24px',height:'24px',borderRadius:'7px',background:featuredJob.grad,display:'none',placeItems:'center'},
      logoNotchStyle: notch,
      starChar: fStar?'★':'☆',
      starStyleLg: {fontSize:'22px',color: fStar?'#ffd66e':'rgba(255,255,255,.5)',cursor:'pointer',background:'none',border:0,padding:0,lineHeight:1,flex:'none'},
      saveLabel: fStar?'★ Saved':'★ Save',
      salary: this.salaryById[featuredJob.id],
      onOpen: () => this.openJob(featuredJob.id),
      onSave: (e) => { e.stopPropagation(); this.toggleStar(featuredJob.id); },
      onDismiss: this.dismissJob(featuredJob.id)
    };
    const queueJobs = ranked.slice(1).map((j,i) => rowView(j, pad(i+2)));
    const savedList = this.jobs.filter(j => starred[j.id]).sort((a,b) => b.score - a.score).map((j,i) => rowView(j, pad(i+1)));
    const stageColor = { Applied:'#2563eb', Screening:'#7c3aed', Interview:'#b45309', Offer:'#15803d', Rejected:'#94a3b8' };
    const appliedListAll = this.jobs.filter(j => applied[j.id]).map(j => {
      const stg = st.stages[j.id] || 'Applied';
      const rem = this._reminderOf(stg);
      return {
        id:j.id, title:j.title, companyLine: j.company+' · '+j.loc, appliedMeta:'Applied 2 days ago',
        logoTileStyle: logoTile,
        logoSrc: 'https://logo.clearbit.com/'+j.domain,
        logoMarkStyle: {width:'23px',height:'23px',borderRadius:'7px',background:markBg(j),display:'grid',placeItems:'center'},
        logoMarkHidden: {width:'23px',height:'23px',borderRadius:'7px',background:markBg(j),display:'none',placeItems:'center'},
        logoNotchStyle: notch,
        stage: stg, stageOptions: this.STAGES, onStageChange: this.onStageSelect(j.id),
        stageDotStyle: {width:'8px',height:'8px',borderRadius:'50%',background: stageColor[stg]||'#2563eb',flex:'none'},
        reminder: rem.text, reminderStyle: {background:rem.bg,color:rem.fg,borderRadius:'7px',padding:'4px 10px',fontSize:'11.5px',fontWeight:600,whiteSpace:'nowrap'},
        atOffer: stg==='Offer',
        onOpen: () => this.openJob(j.id)
      };
    });
    const stageCounts = {}; this.STAGES.forEach(s => stageCounts[s]=0); appliedListAll.forEach(a => { stageCounts[a.stage]=(stageCounts[a.stage]||0)+1; });
    const pipeChips = ['All'].concat(this.STAGES).map(s => {
      const active = st.pipeFilter===s;
      const cnt = s==='All' ? appliedListAll.length : (stageCounts[s]||0);
      return { label:s, count:cnt, active,
        onClick: this.setPipeFilter(s),
        style: {display:'inline-flex',alignItems:'center',gap:'7px',padding:'7px 13px',borderRadius:'10px',fontSize:'13px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap',border:'1px solid '+(active?'#0f1730':'#e2e8f3'),background: active?'#0f1730':'#fff',color: active?'#fff':'#475569'},
        countStyle: {background: active?'rgba(255,255,255,.22)':'#eef2f8',color: active?'#fff':'#64748b',borderRadius:'6px',padding:'1px 7px',fontSize:'11.5px',fontWeight:700} };
    });
    const appliedList = st.pipeFilter==='All' ? appliedListAll : appliedListAll.filter(a => a.stage===st.pipeFilter);

    const salaryChoices = ['No minimum','$40,000','$50,000','$60,000','$70,000','$80,000','$100,000','$120,000','$140,000','$160,000','$180,000','$200,000','$250,000'];
    const alertModes = [
      { v:'top', label:'Top matches only (85%+ fit)' },
      { v:'all', label:'Every new match' },
      { v:'daily', label:'Daily summary' },
      { v:'weekly', label:'Weekly summary' },
      { v:'off', label:'Don\u2019t notify me' }
    ];
    const alertHelpMap = {
      top:'Best of both worlds — you\u2019re pinged the moment a strong match appears, and stay quiet for the rest. Recommended.',
      all:'You\u2019ll hear about every match as it\u2019s found. Can get noisy on busy days.',
      daily:'One roundup each morning with everything JobBot found in the last 24 hours.',
      weekly:'A single digest every Monday — lowest noise, but you may act on roles a little later.',
      off:'No alerts. New matches still appear in your queue whenever you open JobBot.'
    };
    const alertHelp = alertHelpMap[st.alertMode] || alertHelpMap.top;

    const chanStyle = (on) => ({display:'inline-flex',alignItems:'center',gap:'7px',padding:'8px 13px',borderRadius:'10px',fontSize:'13px',fontWeight:600,cursor:'pointer',border:'1px solid '+(on?'#2563eb':'#e2e8f3'),background: on?'#eef4ff':'#fff',color: on?'#2563eb':'#64748b'});
    const alertChannelChips = [
      { key:'email', label:'Email', on: st.alertChannels.email },
      { key:'push', label:'Push', on: st.alertChannels.push },
      { key:'sms', label:'SMS', on: st.alertChannels.sms }
    ].map(c => ({ label: (c.on?'✓ ':'')+c.label, on:c.on, onClick: this.toggleChannel(c.key), style: chanStyle(c.on) }));
    const noChannel = st.alertMode!=='off' && !st.alertChannels.email && !st.alertChannels.push && !st.alertChannels.sms;
    const channelsOff = st.alertMode==='off';
    const excludeChips = st.excludeKeywords.map(kw => ({ kw, onRemove: this.removeExclude(kw) }));
    const blockedChips = st.blockedCompanies.map(c => ({ c, onRemove: this.removeBlock(c) }));
    const ratingChoices = ['Any','3.5★ and up','4★ and up','4.5★ and up'];

    const refusedJobs = st.refused.slice(0,10).map(id => this.jobs.find(j => j.id===id)).filter(Boolean);
    const refusedList = refusedJobs.map((j,i) => { const v = rowView(j, pad(i+1)); v.onRestore = (e) => { if (e) e.stopPropagation(); this.restoreJob(j.id); }; return v; });

    const scanTotal = this.scanSources.length;
    const stage = st.scanStage;
    const scanRows = [];
    this.scanSources.forEach((s,i) => {
      if (i > stage || i >= scanTotal) return;
      const done = i < stage;
      scanRows.push({
        name:s.name, isDone:done, isScanning:!done, foundLabel: s.found+' found',
        rowStyle: {display:'flex',alignItems:'center',gap:'11px',animation:'jbrise .4s ease'},
        iconDoneStyle: {width:'20px',height:'20px',borderRadius:'50%',background:'#dcfce7',color:'#15803d',display:'grid',placeItems:'center',fontSize:'11px',fontWeight:800,flex:'none',animation:'jbpop .3s ease'}
      });
    });
    let scanFound = 0; this.scanSources.forEach((s,i) => { if (i < stage) scanFound += s.found; });
    const scanWidth = Math.min(100, Math.round((stage/scanTotal)*100)) + '%';
    const scanBarStyle = {height:'100%',borderRadius:'3px',background:'linear-gradient(90deg,#2563eb,#22d3ee)',width:scanWidth,transition:'width .45s ease'};

    const cur = this._current();
    const curSrc = this.sourceMeta[cur.source] || { label: cur.source, url: '#' };
    const ci = this.intel[cur.id] || {};
    const resumeSet = {}; (((st.resumes.find(r=>r.def)||st.resumes[0])||{}).detected || []).forEach(s => { resumeSet[s.toLowerCase()] = 1; });
    const reqSkills = ci.req || cur.skills || [];
    const haveArr = reqSkills.filter(s => resumeSet[s.toLowerCase()]);
    const missArr = reqSkills.filter(s => !resumeSet[s.toLowerCase()]);
    const gapPct = reqSkills.length ? Math.round(100 * haveArr.length / reqSkills.length) : 0;
    const curStage = st.stages[cur.id] || (applied[cur.id] ? 'Applied' : null);
    const stageColorD = { Applied:'#2563eb', Screening:'#7c3aed', Interview:'#b45309', Offer:'#15803d', Rejected:'#94a3b8' };
    const ratingFull = ci.rating ? Math.round(ci.rating) : 0;
    const curView = {
      title:cur.title, desc:cur.desc, scoreLabel:cur.score+'%',
      company: cur.company, sourceLabel: curSrc.label, sourceUrl: curSrc.url,
      subline: cur.company+' · '+cur.mode+' · '+cur.loc+' · '+this.salaryById[cur.id],
      logoSrc: 'https://logo.clearbit.com/'+cur.domain,
      logoMarkStyle: {width:'30px',height:'30px',borderRadius:'9px',background:cur.grad,display:'grid',placeItems:'center'},
      logoMarkHidden: {width:'30px',height:'30px',borderRadius:'9px',background:cur.grad,display:'none',placeItems:'center'},
      logoNotchStyle: notch,
      // Company snapshot
      snapInd: ci.ind||'—', snapSize: ci.size||'—', snapFounded: ci.founded||'—', snapFunding: ci.funding||'—',
      snapMedian: ci.medianBase||'—', snapRating: ci.rating ? ci.rating.toFixed(1) : '—', snapReviews: ci.reviews||'',
      snapStars: '★★★★★'.slice(0,ratingFull) + '☆☆☆☆☆'.slice(0,5-ratingFull),
      // Skill gap
      skillsHave: haveArr.map(s=>({name:s})), skillsMiss: missArr.map(s=>({name:s})),
      hasMiss: missArr.length>0, allMatch: missArr.length===0,
      gapText: haveArr.length+' of '+reqSkills.length+' key skills', gapPct: gapPct,
      gapBarStyle: {height:'100%',borderRadius:'4px',width:gapPct+'%',background: gapPct>=66?'#15803d':(gapPct>=40?'#b45309':'#dc2626'),transition:'width .4s ease'},
      // Network
      conns: (ci.conns||[]).map(c => ({ name:c.n, role:c.r, rel:c.rel, initial:c.initial||(c.n||'?')[0] })),
      hasConns: (ci.conns||[]).length>0, noConns: (ci.conns||[]).length===0,
      // Offer / stage
      stage: curStage, isAppliedCur: !!applied[cur.id], atOffer: curStage==='Offer',
      stagePills: this.STAGES.map(s => ({ label:s, active: s===curStage,
        onClick: () => this.setStage(cur.id, s),
        style: {flex:'1',textAlign:'center',padding:'9px 4px',borderRadius:'9px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap',color: s===curStage?'#fff':'#64748b',background: s===curStage?(stageColorD[s]||'#0f1730'):'transparent'} })),
      offerBase: (ci.offer||{}).base||'—', offerEquity: (ci.offer||{}).equity||'—', offerBonus: (ci.offer||{}).bonus||'—',
      offerLow: (ci.offer||{}).low||'—', offerHigh: (ci.offer||{}).high||'—',
      applyBtnLabel: applied[cur.id] ? '✓ In your pipeline — view tracker' : '✓ Mark as applied'
    };

    // ---- Stepper review mode ----
    const rdeck = st.reviewDeck || [];
    const rIdx = st.reviewIdx || 0;
    const rTotal = rdeck.length;
    const rDone = rIdx >= rTotal;
    let reviewView;
    if (rDone || !rTotal) {
      reviewView = { done:true, total:rTotal, savedCount: savedList.length, appliedCount: appliedList.length };
    } else {
      const rj = this.jobs.find(j => j.id===rdeck[rIdx]) || this.jobs[0];
      const rfit = fitOf(rj.score);
      const rci = this.intel[rj.id] || {};
      const rreq = rci.req || rj.skills || [];
      const rhave = rreq.filter(s => resumeSet[s.toLowerCase()]);
      const rgp = rreq.length ? Math.round(100 * rhave.length / rreq.length) : 0;
      const rsrc = this.sourceMeta[rj.source] || { label: rj.source };
      reviewView = {
        done:false, total:rTotal, progressText:(rIdx+1)+' of '+rTotal,
        progressBarStyle:{height:'100%',borderRadius:'3px',background:'linear-gradient(90deg,#2563eb,#22d3ee)',width: Math.round(100*(rIdx+1)/rTotal)+'%',transition:'width .35s ease'},
        title:rj.title, companyLine: rj.company+' · '+rj.mode+' · '+rj.loc,
        salary:this.salaryById[rj.id], scoreLabel:rj.score+'%',
        fitLabel:rfit.label,
        fitStyle: rfit.green ? {background:'#eaf7ee',color:'#15803d',border:'1px solid #bfe6cb',borderRadius:'8px',padding:'4px 11px',fontSize:'12.5px',fontWeight:700,whiteSpace:'nowrap'} : {background:'#eef4ff',color:'#2563eb',border:'1px solid #cfe0ff',borderRadius:'8px',padding:'4px 11px',fontSize:'12.5px',fontWeight:700,whiteSpace:'nowrap'},
        logoSrc: 'https://logo.clearbit.com/'+rj.domain,
        logoMarkHidden: {width:'34px',height:'34px',borderRadius:'10px',background:rj.grad,display:'none',placeItems:'center'},
        logoNotchStyle: notch,
        gapText: rhave.length+' of '+rreq.length+' key skills', gapPct:rgp,
        gapBarStyle:{height:'100%',borderRadius:'4px',width:rgp+'%',background: rgp>=66?'#15803d':(rgp>=40?'#b45309':'#dc2626'),transition:'width .4s ease'},
        sourceLabel: rsrc.label,
        descShort: (rj.desc||'').split('\n')[0]
      };
    }

    const suggestions = this.suggData.map((s,i) => ({
      txt:s.txt, why:s.why, check: st.suggSel[i] ? '✓' : '',
      onToggle: () => this.toggleSugg(i),
      boxStyle: {width:'20px',height:'20px',flex:'none',borderRadius:'6px',border: st.suggSel[i] ? '0' : '1.5px solid #cbd5e1', background: st.suggSel[i] ? '#2563eb' : '#fff', color:'#fff', display:'grid', placeItems:'center', fontSize:'12px', fontWeight:800, cursor:'pointer', marginTop:'2px'}
    }));

    const resumesView = st.resumes.map(r => ({
      id:r.id, name:r.name, type:r.type, meta:r.meta, isDefault:r.def, notDefault:!r.def,
      tileStyle: {width:'42px',height:'52px',borderRadius:'8px',background:r.type==='PDF'?'#fee2e2':'#dbeafe',color:r.type==='PDF'?'#b91c1c':'#1d4ed8',display:'grid',placeItems:'center',fontSize:r.type==='PDF'?'11px':'10px',fontWeight:800,flex:'none'},
      onDelete: () => this.setState(s => ({resumes:s.resumes.filter(x => x.id!==r.id)})),
      onDefault: () => { this.setState(s => ({resumes:s.resumes.map(x => ({...x, def:x.id===r.id}))})); this.showFlash('success','Default resume updated.'); }
    }));

    const keywords = st.keywords.map(k => ({ k, onRemove: () => this.setState(s => ({keywords:s.keywords.filter(x => x!==k)})) }));
    const kwSet = {}; st.keywords.forEach(k => { kwSet[k] = true; });

    // ---- Location picker (filterable comboboxes) ----
    const lq = (st.locQuery || '').toLowerCase();
    const optStyle = (sel) => ({padding:'9px 11px',fontSize:'13.5px',cursor:'pointer',borderRadius:'8px',color: sel?'#2563eb':'#1f2a44',background: sel?'#eef4ff':'transparent',fontWeight: sel?600:500});
    const mkOpts = (arr, selVal, pick) => arr.filter(x => x.toLowerCase().indexOf(lq) >= 0).map(x => ({ name:x, onPick:(e)=>{ if(e) e.stopPropagation(); pick(x); }, style: optStyle(x===selVal) }));
    const curCountry = this.countriesData.find(c => c.country === st.loc.country) || this.countriesData[0];
    const regionLabel = curCountry.regionLabel || 'State';
    const regionLabelLC = regionLabel.toLowerCase();
    const curRegion = (curCountry.regions || []).find(r => r.state === st.loc.region);
    const countryOpts = mkOpts(this.countriesData.map(c=>c.country), st.loc.country, this.pickCountry);
    const regionOpts = mkOpts((curCountry.regions || []).map(r=>r.state), st.loc.region, this.pickRegion);
    const cityOpts = mkOpts(curRegion ? curRegion.cities : [], st.loc.city, this.pickCity);
    const radiusOpts = mkOpts(['5 miles','10 miles','25 miles','50 miles','100 miles','Anywhere in region'], st.loc.radius, this.pickRadius);
    // Free-entry fallback: any typed region/city not already listed is still selectable (covers every country, county, town).
    const qTrim = (st.locQuery || '').trim();
    if (st.locOpen === 'region' && qTrim && !regionOpts.some(o => o.name.toLowerCase() === lq)) {
      regionOpts.unshift({ name:'Use \u201c'+qTrim+'\u201d', onPick:(e)=>{ if(e) e.stopPropagation(); this.pickRegion(qTrim); }, style: Object.assign(optStyle(false), {color:'#2563eb',fontWeight:600}) });
    }
    if (st.locOpen === 'city' && qTrim && !cityOpts.some(o => o.name.toLowerCase() === lq)) {
      cityOpts.unshift({ name:'Use \u201c'+qTrim+'\u201d', onPick:(e)=>{ if(e) e.stopPropagation(); this.pickCity(qTrim); }, style: Object.assign(optStyle(false), {color:'#2563eb',fontWeight:600}) });
    }
    const valStyle = (ph) => ({color: ph?'#9ca3af':'#1f2a44', fontWeight: ph?500:600, fontSize:'14px', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'});
    const fieldStyle = (dis) => ({display:'flex',alignItems:'center',justifyContent:'space-between',gap:'8px',width:'100%',boxSizing:'border-box',padding:'11px 13px',border:'1px solid #e2e8f3',borderRadius:'11px',background: dis?'#f5f7fb':'#fff',cursor: dis?'not-allowed':'pointer'});
    const regionDisabled = !st.loc.country;
    const cityDisabled = !st.loc.region;
    const locCombos = [
      { key:'country', label:'Country', value: st.loc.country || 'Select a country', valueStyle: valStyle(!st.loc.country),
        open: st.locOpen==='country', closed: st.locOpen!=='country', fieldStyle: fieldStyle(false),
        onOpen: this.openCombo('country'), options: countryOpts, noMatch: countryOpts.length===0, placeholder:'Type a country…' },
      { key:'region', label: regionLabel, value: st.loc.region || ('Select a '+regionLabelLC), valueStyle: valStyle(!st.loc.region),
        open: st.locOpen==='region', closed: st.locOpen!=='region', fieldStyle: fieldStyle(regionDisabled),
        onOpen: regionDisabled ? (()=>{}) : this.openCombo('region'), options: regionOpts, noMatch: regionOpts.length===0, placeholder:'Type a '+regionLabelLC+'…' },
      { key:'city', label:'City', value: cityDisabled ? ('Pick a '+regionLabelLC+' first') : (st.loc.city || 'Select a city'), valueStyle: valStyle(cityDisabled || !st.loc.city),
        open: st.locOpen==='city', closed: st.locOpen!=='city', fieldStyle: fieldStyle(cityDisabled),
        onOpen: cityDisabled ? (()=>{}) : this.openCombo('city'), options: cityOpts, noMatch: cityOpts.length===0, placeholder:'Type a city…' },
      { key:'radius', label:'Search radius', value: st.loc.radius, valueStyle: valStyle(false),
        open: st.locOpen==='radius', closed: st.locOpen!=='radius', fieldStyle: fieldStyle(cityDisabled),
        onOpen: cityDisabled ? (()=>{}) : this.openCombo('radius'), options: radiusOpts, noMatch: radiusOpts.length===0, placeholder:'Filter…' }
    ];
    const suggestGroups = this.suggestGroups.map(g => ({
      label: g.label,
      chips: g.words.map(w => {
        const on = !!kwSet[w];
        return {
          word: w, prefix: on ? '✓ ' : '+ ',
          style: on
            ? {background:'#eaf1ff',color:'#2563eb',border:'1px solid #cfe0ff',borderRadius:'8px',padding:'5px 11px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap'}
            : {background:'#fff',color:'#475569',border:'1px solid #e2e8f3',borderRadius:'8px',padding:'5px 11px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap'},
          onToggle: () => this.setState(s2 => ({ keywords: s2.keywords.indexOf(w) >= 0 ? s2.keywords.filter(x => x !== w) : [...s2.keywords, w] }))
        };
      })
    }));
    const defResume = st.resumes.find(r => r.def) || st.resumes[0];
    const resumeName = defResume ? defResume.name : '';
    const resumeSkills = (defResume && defResume.detected) ? defResume.detected : [];
    const resumeChips = resumeSkills.map(w => { const on = !!kwSet[w]; return {
      word:w, prefix: on?'✓ ':'+ ',
      style: {background: on?'#dbe7ff':'#eef4ff',color:'#2563eb',border:'1px solid #cfe0ff',borderRadius:'8px',padding:'5px 11px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap'},
      onToggle: () => this.setState(s2 => ({ keywords: s2.keywords.indexOf(w)>=0 ? s2.keywords.filter(x=>x!==w) : [...s2.keywords, w] }))
    }; });
    const hasResumeSkills = resumeChips.length > 0;
    const chipStyle = (on) => on
      ? {background:'#eaf1ff',color:'#2563eb',border:'1px solid #cfe0ff',borderRadius:'8px',padding:'5px 11px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap'}
      : {background:'#fff',color:'#475569',border:'1px solid #e2e8f3',borderRadius:'8px',padding:'5px 11px',fontSize:'12.5px',fontWeight:600,cursor:'pointer',whiteSpace:'nowrap'};
    const multi = (key, opts) => opts.map(o => ({ label:o, style: chipStyle(st[key].indexOf(o)>=0), onToggle: this.toggleIn(key,o) }));
    const expChips = multi('expLevels', ['Internship','Entry','Associate','Mid','Senior','Lead','Manager','Director']);
    const typeChips = multi('jobTypes', ['Full-time','Part-time','Contract','Temporary','Internship']);
    const sizeChips = multi('companySizes', ['Startup (1–50)','Mid (51–500)','Large (500+)']);
    const industryChips = multi('industries', ['Tech','Finance','Healthcare','Education','Government','Retail','Media']);
    const dpChips = ['Any time','Past 24h','Past week','Past month'].map(o => ({ label:o, style: seg(st.datePosted===o), onClick: this.setDatePosted(o) }));
    const toggles = [
      { key:'easyApply', label:'Easy apply only', desc:'Hide jobs with long external forms' },
      { key:'sponsorship', label:'Offers visa sponsorship', desc:'Only roles open to sponsorship' },
      { key:'excludeAgencies', label:'Exclude staffing agencies', desc:'Skip recruiter & agency listings' }
    ].map(t => { const on = !!st[t.key]; return {
      label:t.label, desc:t.desc, onToggle: this.toggleBool(t.key),
      trackStyle: {width:'42px',height:'24px',borderRadius:'999px',background: on?'#2563eb':'#d4ddec',position:'relative',cursor:'pointer',transition:'background .2s',flex:'none'},
      knobStyle: {width:'18px',height:'18px',borderRadius:'50%',background:'#fff',position:'absolute',top:'3px',left: on?'21px':'3px',transition:'left .2s',boxShadow:'0 1px 2px rgba(0,0,0,.2)'}
    }; });
    const hasResume = st.resumes.length > 0;
    const flash = st.flash;
    const newToday = this.jobs.filter(j => j.isNew).length;
    const weeklyRaw = [42,66,30,80,54,90,72];
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const wmax = Math.max.apply(null, weeklyRaw);
    const weeklyBars = weeklyRaw.map((v,i) => ({ label: days[i], barStyle: {width:'100%',height:v+'%',borderRadius:'6px 6px 3px 3px',minHeight:'8px',background: dark ? (v===wmax ? '#34405C' : '#2A3550') : (i===weeklyRaw.length-1 ? 'linear-gradient(180deg,#2563eb,#22d3ee)' : '#dbe7ff')} }));
    const goReview = this.enterReview;
    const tkMap = {
      modern: { accent:'#2563eb', align:'left', twoCol:false, font:'-apple-system,system-ui,sans-serif', bar:true, railBg:'#eef4ff' },
      classic:{ accent:'#0f1730', align:'center', twoCol:false, font:"Georgia,'Times New Roman',serif", bar:false, railBg:'#f3f4f6' },
      twocol: { accent:'#0d9488', align:'left', twoCol:true, font:'-apple-system,system-ui,sans-serif', bar:false, railBg:'#ecfdf8' },
      minimal:{ accent:'#475569', align:'left', twoCol:false, font:'-apple-system,system-ui,sans-serif', bar:false, railBg:'#f8fafc' }
    };
    const tk = tkMap[st.builderTemplate] || tkMap.modern;
    const builderCards = this.builderTemplates.map(t => ({
      id:t.id, name:t.name, tag:t.tag,
      tModern:t.id==='modern', tClassic:t.id==='classic', tTwoCol:t.id==='twocol', tMinimal:t.id==='minimal',
      onSelect: this.selectTemplate(t.id),
      cardStyle: { border: st.builderTemplate===t.id ? '2px solid #2563eb' : '1px solid #e6ecf6', borderRadius:'14px', padding:'10px', background:'#fff', cursor:'pointer', boxShadow: st.builderTemplate===t.id ? '0 14px 30px -18px rgba(37,99,235,.5)' : '0 12px 30px -26px rgba(15,23,48,.3)' },
      nameStyle: { fontWeight:700, fontSize:'13px', marginTop:'8px', color: st.builderTemplate===t.id ? '#2563eb' : '#0f1730' }
    }));
    const bWorking = st.builderPhase==='working';
    const rdName = this._fileToName(defResume && defResume.name);
    const builtFromName = defResume ? defResume.name : (this.props.userName ? this.props.userName + '’s resume' : 'your resume');
    const previewBar = tk.bar;
    const previewPaperStyle = { background:'#fff', borderRadius:'10px', padding:'30px 30px 34px', fontFamily: tk.font, boxShadow:'0 18px 44px -26px rgba(15,23,48,.45)', border:'1px solid #eef2f8' };
    const previewBarStyle = { height:'6px', borderRadius:'4px', background: tk.accent, marginBottom:'16px', width:'80px' };
    const previewNameStyle = { fontWeight:700, fontSize:'24px', letterSpacing:'-.02em', color:'#0f1730', textAlign: tk.align, fontFamily: tk.font };
    const previewTitleStyle = { fontSize:'13px', fontWeight:600, color: tk.accent, textAlign: tk.align, marginTop:'2px' };
    const previewContactStyle = { fontSize:'11px', color:'#64748b', textAlign: tk.align, marginTop:'5px' };
    const previewHeadStyle = { fontWeight:700, fontSize:'11px', letterSpacing:'.1em', textTransform:'uppercase', color: tk.accent, borderBottom:'1px solid #e6ecf6', paddingBottom:'5px', margin:'18px 0 9px' };
    const previewChipStyle = { display:'inline-block', background:'#f1f5fb', color: tk.accent, border:'1px solid #e2e8f3', borderRadius:'6px', padding:'2px 8px', fontSize:'11px', fontWeight:600, marginRight:'5px', marginBottom:'5px' };
    const previewRailStyle = { background: tk.railBg, borderRadius:'8px', padding:'16px', width:'36%', flex:'none' };
    const reformatLabel = bWorking ? 'Reformatting…' : (st.builderPhase==='done' ? '✓ Reformat again' : '✨ Reformat my resume');

    const onbSteps = [
      { emoji:'👋', title:'Welcome aboard, '+first+'!', body:"JobBot does the job hunting so you don't have to. Here's the 20-second tour — or skip it, your call." },
      { emoji:'📄', title:'Start with your resume', body:'Drop it in once and we match every new role to your experience — with a fit score and the reasons why.' },
      { emoji:'✨', title:'Only the good stuff', body:'We surface a short, ranked shortlist each day and text or email you when something strong lands. No noise, no spam.' }
    ];
    const onbCur = onbSteps[st.onbStep] || onbSteps[0];
    const onbDots = onbSteps.map((s,i) => ({ style: {width: i===st.onbStep?'22px':'7px', height:'7px', borderRadius:'4px', background: i===st.onbStep?'#ea7317':'#f0d4b4', transition:'all .25s ease'} }));

    // ---- Insights / analytics ----
    const viewCounts = { j1:34, j5:22, j4:18, j2:15, j6:11, j3:7 };
    const avgFit = Math.round(this.jobs.reduce((s,j)=>s+j.score,0)/this.jobs.length);
    const insightKpis = [
      { label:'Profile views', value:'47', sub:'▲ 12 this week', accent:'#38BDF8' },
      { label:'Recruiter views', value:'8', sub:'across 6 companies', accent:'#38BDF8' },
      { label:'Avg match score', value: avgFit+'%', sub:'on your matches', accent:'#4ADE80' },
      { label:'Saved → applied', value:'40%', sub:'2 of 5 saved', accent:'#FB923C' }
    ].map(k => ({ ...k, valueStyle:{fontFamily:"'Space Grotesk',sans-serif",fontWeight:700,fontSize:'30px',letterSpacing:'-.03em',color:k.accent,lineHeight:1,marginTop:'8px'} }));
    const mostViewed = [...this.jobs].sort((a,b)=>(viewCounts[b.id]||0)-(viewCounts[a.id]||0)).slice(0,4).map((j,i)=>{
      const v = viewCounts[j.id]||0;
      return { title:j.title, company:j.company, views:v, fit:j.score+'%',
        logoSrc:'https://logo.clearbit.com/'+j.domain, logoMarkHidden:{width:'22px',height:'22px',borderRadius:'7px',background:markBg(j),display:'none',placeItems:'center'}, logoNotchStyle:notch,
        logoTileStyle:{width:'40px',height:'40px',flex:'none',borderRadius:'11px',background:dark?'#1E2D45':'#fff',border:'1px solid '+(dark?'#1E2D45':'#e6ecf6'),display:'grid',placeItems:'center'},
        barStyle:{height:'6px',borderRadius:'3px',background:'#38BDF8',width:Math.round(100*v/34)+'%',transition:'width .4s ease'} };
    });
    const recruiterViews = [
      { co:'Stripe', what:'Recruiter viewed your profile', when:'2h ago', domain:'stripe.com' },
      { co:'Datadog', what:'Hiring manager opened your resume', when:'1d ago', domain:'datadoghq.com' },
      { co:'Figma', what:'Recruiter viewed your profile', when:'3d ago', domain:'figma.com' }
    ].map(r => ({ ...r, logoSrc:'https://logo.clearbit.com/'+r.domain,
      tileStyle:{width:'38px',height:'38px',flex:'none',borderRadius:'10px',background:dark?'#1E2D45':'#fff',border:'1px solid '+(dark?'#1E2D45':'#e6ecf6'),display:'grid',placeItems:'center',fontWeight:700,color:'#38BDF8'} }));
    // Match-activity weeks (0 = this week) + today highlight
    const weeksData = [ [42,66,30,80,54,90,72], [30,48,52,40,66,58,44], [55,38,60,72,49,80,63], [20,34,28,45,39,52,41] ];
    const weekLabels = ['This week','Last week','2 weeks ago','3 weeks ago'];
    const dayLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const todayIdx = (new Date().getDay() + 6) % 7;
    const wk = Math.min(3, Math.max(0, st.insightWeek||0));
    const _now = new Date(); _now.setHours(0,0,0,0);
    const _mon = new Date(_now); _mon.setDate(_now.getDate() - todayIdx - 7*wk);
    const _fmt = (d) => (d.getMonth()+1)+'/'+d.getDate();
    const _sun = new Date(_mon); _sun.setDate(_mon.getDate() + 6);
    const insightWeekRange = _fmt(_mon) + ' – ' + _fmt(_sun);
    const insightsBars = weeksData[wk].map((v,i) => {
      const isToday = i===todayIdx && wk===0;
      const d = new Date(_mon); d.setDate(_mon.getDate() + i);
      return { label: dayLabels[i], date: _fmt(d),
        barStyle: {width:'100%',height:v+'%',borderRadius:'6px 6px 3px 3px',minHeight:'8px',background: isToday ? '#38BDF8' : (dark?'#2A3550':'#dbe7ff'), transition:'height .35s ease, background .2s'},
        dotStyle: {fontSize:'10.5px',fontWeight: isToday?700:600,color: isToday?'#38BDF8':'#94a3b8'},
        dateStyle: {fontSize:'9.5px',fontWeight:500,color: isToday?'#38BDF8':'#64748b'} };
    });
    const weekOptions = weekLabels.map((l,i) => ({ value:i, label:l }));
    const insightWeekLabel = weekLabels[wk];

    return {
      isLogin: st.screen==='login', isApp: st.screen!=='login' && st.screen!=='splash',
      isSplash: st.screen==='splash', getStarted: this.go('login'),
      greeting: part+', '+first+' 👋',
      avatarText: (first[0]||'Y').toUpperCase(), userEmail: st.profile.email, userFirst:first,
      hasAvatar: !!st.profilePic, noAvatar: !st.profilePic, avatarImg: st.profilePic,
      editProfile: st.editProfile, openEditProfile:this.openEditProfile, closeEditProfile:this.closeEditProfile, saveProfile:this.saveProfile,
      profileName: st.profile.name, profileEmail: st.profile.email, profilePhone: st.profile.phone, profileLocation: st.profile.location, profileHeadline: st.profile.headline,
      onProfileName:this.onProfileField('name'), onProfileEmail:this.onProfileField('email'), onProfilePhone:this.onProfileField('phone'), onProfileLocation:this.onProfileField('location'), onProfileHeadline:this.onProfileField('headline'),
      onProfilePic:this.onProfilePic, removeProfilePic:this.removeProfilePic,
      stopProp: (e) => { if (e && e.stopPropagation) e.stopPropagation(); },
      signIn:this.signIn,
      isSignIn: st.authMode!=='signup', isSignUp: st.authMode==='signup', toSignIn:this.setAuth('signin'), toSignUp:this.setAuth('signup'),
      authEntry: st.authStep==='entry', authCodeStep: st.authStep==='code', authSmsStep: st.authStep==='code2',
      authContact: st.authContact, onAuthContact:this.onAuthContact,
      authPhone: st.authPhone, onAuthPhone:this.onAuthPhone,
      twoFactor: st.twoFactor, toggleTwoFactor:this.toggleTwoFactor,
      tfTrackStyle: {width:'42px',height:'24px',borderRadius:'999px',background: st.twoFactor?'#2563eb':'#d4ddec',position:'relative',cursor:'pointer',transition:'background .2s',flex:'none'},
      tfKnobStyle: {width:'18px',height:'18px',borderRadius:'50%',background:'#fff',position:'absolute',top:'3px',left: st.twoFactor?'21px':'3px',transition:'left .2s',boxShadow:'0 1px 2px rgba(0,0,0,.2)'},
      emailInputStyle: Object.assign({width:'100%',padding:'11px 13px',borderRadius:'11px',fontFamily:'inherit',fontSize:'inherit',background:'#fff',outline:'none',border:'1px solid '+((st.authError&&st.authErrorField==='email')?'#dc2626':'#e2e8f3')}, (st.authError&&st.authErrorField==='email')?{animation:'jbshake .4s', boxShadow:'0 0 0 3px rgba(220,38,38,.12)'}:{}),
      phoneInputStyle: Object.assign({width:'100%',padding:'11px 13px',borderRadius:'11px',fontFamily:'inherit',fontSize:'inherit',background:'#fff',outline:'none',border:'1px solid '+((st.authError&&st.authErrorField==='phone')?'#dc2626':'#e2e8f3')}, (st.authError&&st.authErrorField==='phone')?{animation:'jbshake .4s', boxShadow:'0 0 0 3px rgba(220,38,38,.12)'}:{}),
      emailError: st.authError && st.authErrorField==='email',
      phoneError: st.authError && st.authErrorField==='phone',
      sentToEmail: st.authContact || 'your email',
      sentToPhone: st.authPhone || 'your phone',
      sendCode:this.sendCode, verifyEmailCode:this.verifyEmailCode, resendCode:this.resendCode, backToEntry:this.backToEntry, backToCode:this.backToCode, onCodeInput:this.onCodeInput, onCodeKey:this.onCodeKey,
      verifyEmailLabel: st.twoFactor ? 'Verify & continue →' : 'Verify & continue',
      entryTitle: st.authMode==='signup'?'Create your account':'Sign in',
      entrySub: st.authMode==='signup'?"Set up JobBot and we'll start hunting today — no password needed.":"We'll email you a one-time code — no password needed.",
      navMatches:navItem(onMatches), navResumes:navItem(st.screen==='resumes'), navPrefs:navItem(st.screen==='preferences'), navOptions:navItem(st.screen==='options'),
      goMatches:this.go('dashboard'), goResumes:this.go('resumes'), goPrefs:this.go('preferences'), goOptions:this.go('options'), goLogin:this.go('login'),
      screenDashboard: st.screen==='dashboard', screenJob: st.screen==='job', screenResumes: st.screen==='resumes', screenPrefs: st.screen==='preferences', screenOptions: st.screen==='options',
      saveOptions:this.saveOptions, deleteAccount:this.deleteAccount,
      shellDark: dark ? 'jb-dark' : '',
      isOnboarding: st.onboarding,
      onbEmoji: onbCur.emoji, onbTitle: onbCur.title, onbBody: onbCur.body,
      onbDots, onbBtnLabel: (st.onbStep>=2?'Take me to JobBot →':'Next'), showOnbBack: st.onbStep>0,
      onbNext:this.onbNext, onbBack:this.onbBack, onbSkip:this.onbSkip,      themeSeg: (t) => ({flex:'1',textAlign:'center',padding:'9px',borderRadius:'9px',fontSize:'13px',fontWeight:600,cursor:'pointer',color: st.theme===t?'#0f1730':'#8294b5',background: st.theme===t?'#fff':'transparent',boxShadow: st.theme===t?'0 1px 3px rgba(15,23,48,.12)':'none'}),
      themeLight: {flex:'1',textAlign:'center',padding:'9px',borderRadius:'9px',fontSize:'13px',fontWeight:600,cursor:'pointer',color: st.theme==='light'?'#0f1730':'#8294b5',background: st.theme==='light'?'#fff':'transparent',boxShadow: st.theme==='light'?'0 1px 3px rgba(15,23,48,.12)':'none'},
      themeDark: {flex:'1',textAlign:'center',padding:'9px',borderRadius:'9px',fontSize:'13px',fontWeight:600,cursor:'pointer',color: st.theme==='dark'?'#0f1730':'#8294b5',background: st.theme==='dark'?'#fff':'transparent',boxShadow: st.theme==='dark'?'0 1px 3px rgba(15,23,48,.12)':'none'},
      themeSystem: {flex:'1',textAlign:'center',padding:'9px',borderRadius:'9px',fontSize:'13px',fontWeight:600,cursor:'pointer',color: st.theme==='system'?'#0f1730':'#8294b5',background: st.theme==='system'?'#fff':'transparent',boxShadow: st.theme==='system'?'0 1px 3px rgba(15,23,48,.12)':'none'},
      setLight:this.setTheme('light'), setDark:this.setTheme('dark'), setSystem:this.setTheme('system'),
      optToggles: [
        { key:'jobAlertEmail', label:'Job match alerts', desc:'Email me when JobBot finds a strong match' },
        { key:'weeklyEmail', label:'Weekly summary', desc:'A Monday digest of the week\u2019s activity' },
        { key:'prodUpdates', label:'Product updates', desc:'Occasional news about new JobBot features' }
      ].map(t => { const on = !!st[t.key]; return {
        label:t.label, desc:t.desc, onToggle: this.toggleBool(t.key),
        trackStyle: {width:'42px',height:'24px',borderRadius:'999px',background: on?'#2563eb':'#d4ddec',position:'relative',cursor:'pointer',transition:'background .2s',flex:'none'},
        knobStyle: {width:'18px',height:'18px',borderRadius:'50%',background:'#fff',position:'absolute',top:'3px',left: on?'21px':'3px',transition:'left .2s',boxShadow:'0 1px 2px rgba(0,0,0,.2)'}
      }; }),
      refresh:this.refresh, markApplied:this.markApplied,
      screenHome: st.screen==='home', goHome:this.go('home'), navHome:navItem(st.screen==='home'),
      homeNewToday:newToday, homeNewWeek:23, homeSaved:savedList.length, homeApplied:appliedList.length,
      weeklyBars, goReview,
      goForYou:this.goTab('foryou'), goSavedTab:this.goTab('saved'), goAppliedTab:this.goTab('applied'),
      goInsights:this.go('insights'), screenInsights: st.screen==='insights',
      insightKpis, mostViewed, recruiterViews, insightsBars,
      weekOptions, insightWeek: wk, insightWeekLabel, insightWeekRange, onWeekSelect:this.onWeekSelect, weekPrev:this.weekPrev, weekNext:this.weekNext, canNewer: wk>0, canOlder: wk<3,
      screenReview: st.screen==='review', review: reviewView, reviewActive: !reviewView.done,
      reviewKeep:this.reviewKeep, reviewSkip:this.reviewSkip, reviewApplyStep:this.reviewApplyStep, reviewOpen:this.reviewOpen, exitReview:this.exitReview,
      screenBuilder: st.screen==='builder', goBuilder:this.go('builder'),
      builderCards, rd: {...this.resumeData, name: rdName}, builtFromName, onLogoError:this.onLogoError, reformat:this.reformat, reformatLabel, saveBuilt:this.saveBuilt,
      bIdle: st.builderPhase==='idle', bWorking: st.builderPhase==='working', bDone: st.builderPhase==='done',
      previewSingle: !tk.twoCol, previewTwoCol: tk.twoCol, previewBar,
      previewPaperStyle, previewBarStyle, previewNameStyle, previewTitleStyle, previewContactStyle, previewHeadStyle, previewChipStyle, previewRailStyle,
      setForYou:this.setTab('foryou'), setSaved:this.setTab('saved'), setApplied:this.setTab('applied'), setRefused:this.setTab('refused'),
      isForYou: st.tab==='foryou', isSaved: st.tab==='saved', isApplied: st.tab==='applied', isRefused: st.tab==='refused',
      tabForYou:this._tabStyle(st.tab==='foryou'), tabSaved:this._tabStyle(st.tab==='saved'), tabApplied:this._tabStyle(st.tab==='applied'), tabRefused:this._tabStyle(st.tab==='refused'),
      savedCount: savedList.length, appliedCount: appliedList.length,
      refusedList, refusedCount: refusedList.length, hasRefused: refusedList.length>0, noRefused: refusedList.length===0,
      notInterested:this.notInterested,
      dashHome: !hasResume,
      dashScan: hasResume && st.scanning,
      scanRows, scanTotal, scanFound, scanBarStyle,
      dashForYou: hasResume && !st.scanning,
      featured, queueJobs, queueCount: queueJobs.length,
      savedList, hasSaved: savedList.length>0, noSaved: savedList.length===0,
      appliedList, hasApplied: appliedList.length>0, noApplied: appliedList.length===0,
      pipeChips, pipeHasAny: appliedListAll.length>0,
      homeZoneStyle:this._zone(st.dragHome), onDropHome:this.onDropHome, dragHomeOn:this.dragHomeOn, dragHomeOff:this.dragHomeOff, onPickHome:this.onPickHome,
      cur:curView, suggestions,
      applyEdits:this.applyEdits, applyLabel: st.appliedEdits ? '✓ Edits applied' : 'Apply selected edits', applyStyle:this._applyStyle(st.appliedEdits),
      questionText:'Why do you want to work at '+cur.company+'?', draftValue:st.draft, onDraftInput:this.onDraftInput, draftAnswer:this.draftAnswer, drafting:st.drafting, notDrafting:!st.drafting,
      back:this.back,
      resumesView, resumeCount: st.resumes.length,
      resZoneStyle:this._zone(st.dragRes), onDropRes:this.onDropRes, dragResOn:this.dragResOn, dragResOff:this.dragResOff, onPickRes:this.onPickRes,
      keywords, suggestGroups, resumeChips, hasResumeSkills, resumeName,
      salaryChoices, minSalary: st.minSalary, onMinSalary: this.onMinSalary,
      alertModes, alertMode: st.alertMode, onAlertMode: this.onAlertMode, alertHelp,
      alertChannelChips, noChannel, channelsOff,
      excludeChips, excludeDraft: st.excludeDraft, onExcludeDraft: this.onExcludeDraft, addExclude: this.addExclude,
      blockedChips, blockDraft: st.blockDraft, onBlockDraft: this.onBlockDraft, addBlock: this.addBlock,
      ratingChoices, minRating: st.minRating, onMinRating: this.onMinRating,
      locCombos, locQuery: st.locQuery, onLocType: this.onLocType, closeCombo: this.closeCombo,
      suggestOpen: st.suggestOpen, toggleSuggest: this.toggleSuggest,
      suggestArrowStyle: { display:'inline-flex', transition:'transform .2s ease', transform: st.suggestOpen ? 'rotate(0deg)' : 'rotate(180deg)', color:'#8294b5', fontSize:'12px', lineHeight:1 },
      expChips, typeChips, sizeChips, industryChips, dpChips, toggles,
      wtRemote:seg(st.workType==='Remote'), wtHybrid:seg(st.workType==='Hybrid'), wtOnsite:seg(st.workType==='On-site'),
      setRemote:this.setWorkType('Remote'), setHybrid:this.setWorkType('Hybrid'), setOnsite:this.setWorkType('On-site'), savePrefs:this.savePrefs,
      hasFlash: !!flash, flashMsg: flash ? flash.msg : '', flashStyle:this._flashStyle(flash)
    };
  }
}
