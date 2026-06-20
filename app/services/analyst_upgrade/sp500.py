"""标普 500 分析师目标价持续上调筛选服务."""

import asyncio
from datetime import date, timedelta

import httpx

from app.core.logging import logger
from app.schemas.analyst_upgrade import SP500UpgradesResponse, UpgradeStock
from app.services.analyst_upgrade.nasdaq100 import (
    _WIKI_HEADERS,
    _WIKI_RETRIES,
    _compute_recent_points,
    _fetch_summary,
    _is_monotonic_up,
    _parse_wiki_html,
    _pct,
)

_WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_WIKI_SP500_API_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=parse&page=List_of_S%26P_500_companies&format=json&prop=text&formatversion=2"
)
_CONCURRENCY = 20

# 兜底列表：覆盖标普 500 中分析师覆盖度高的主要成分股
# 已包含纳斯达克 100 重叠成分（AAPL/MSFT 等），以及金融、医疗、能源等独有板块
_FALLBACK_SP500: list[tuple[str, str, str]] = [
    # 信息技术
    ("AAPL", "Apple Inc.",                            "Technology"),
    ("ACN",  "Accenture",                             "Technology"),
    ("ADBE", "Adobe Inc.",                            "Technology"),
    ("ADI",  "Analog Devices",                        "Technology"),
    ("ADSK", "Autodesk",                              "Technology"),
    ("AKAM", "Akamai Technologies",                   "Technology"),
    ("AMAT", "Applied Materials",                     "Technology"),
    ("AMD",  "Advanced Micro Devices",                "Technology"),
    ("ANET", "Arista Networks",                       "Technology"),
    ("APH",  "Amphenol",                              "Technology"),
    ("APP",  "AppLovin",                              "Technology"),
    ("AVGO", "Broadcom",                              "Technology"),
    ("CDNS", "Cadence Design Systems",                "Technology"),
    ("CDW",  "CDW Corporation",                       "Technology"),
    ("CIEN", "Ciena",                                 "Technology"),
    ("COHR", "Coherent Corp.",                        "Technology"),
    ("CRM",  "Salesforce",                            "Technology"),
    ("CRWD", "CrowdStrike",                           "Technology"),
    ("CSCO", "Cisco",                                 "Technology"),
    ("CTSH", "Cognizant",                             "Technology"),
    ("DDOG", "Datadog",                               "Technology"),
    ("DELL", "Dell Technologies",                     "Technology"),
    ("FFIV", "F5, Inc.",                              "Technology"),
    ("FICO", "Fair Isaac",                            "Technology"),
    ("FSLR", "First Solar",                           "Technology"),
    ("FTNT", "Fortinet",                              "Technology"),
    ("GDDY", "GoDaddy",                               "Technology"),
    ("GEN",  "Gen Digital",                           "Technology"),
    ("GLW",  "Corning Inc.",                          "Technology"),
    ("HPE",  "Hewlett Packard Enterprise",            "Technology"),
    ("HPQ",  "HP Inc.",                               "Technology"),
    ("IBM",  "IBM",                                   "Technology"),
    ("INTC", "Intel",                                 "Technology"),
    ("INTU", "Intuit",                                "Technology"),
    ("IT",   "Gartner",                               "Technology"),
    ("JBL",  "Jabil",                                 "Technology"),
    ("KEYS", "Keysight Technologies",                 "Technology"),
    ("KLAC", "KLA Corporation",                       "Technology"),
    ("LITE", "Lumentum",                              "Technology"),
    ("LRCX", "Lam Research",                          "Technology"),
    ("MCHP", "Microchip Technology",                  "Technology"),
    ("MPWR", "Monolithic Power Systems",              "Technology"),
    ("MSFT", "Microsoft",                             "Technology"),
    ("MSI",  "Motorola Solutions",                    "Technology"),
    ("MU",   "Micron Technology",                     "Technology"),
    ("NOW",  "ServiceNow",                            "Technology"),
    ("NTAP", "NetApp",                                "Technology"),
    ("NVDA", "Nvidia",                                "Technology"),
    ("NXPI", "NXP Semiconductors",                    "Technology"),
    ("ON",   "ON Semiconductor",                      "Technology"),
    ("ORCL", "Oracle Corporation",                    "Technology"),
    ("PANW", "Palo Alto Networks",                    "Technology"),
    ("PLTR", "Palantir Technologies",                 "Technology"),
    ("PTC",  "PTC Inc.",                              "Technology"),
    ("Q",    "Qnity Electronics",                     "Technology"),
    ("QCOM", "Qualcomm",                              "Technology"),
    ("ROP",  "Roper Technologies",                    "Technology"),
    ("SMCI", "Supermicro",                            "Technology"),
    ("SNDK", "Sandisk",                               "Technology"),
    ("SNPS", "Synopsys",                              "Technology"),
    ("STX",  "Seagate Technology",                    "Technology"),
    ("SWKS", "Skyworks Solutions",                    "Technology"),
    ("TDY",  "Teledyne Technologies",                 "Technology"),
    ("TEL",  "TE Connectivity",                       "Technology"),
    ("TER",  "Teradyne",                              "Technology"),
    ("TRMB", "Trimble Inc.",                          "Technology"),
    ("TXN",  "Texas Instruments",                     "Technology"),
    ("TYL",  "Tyler Technologies",                    "Technology"),
    ("VRSN", "Verisign",                              "Technology"),
    ("WDAY", "Workday, Inc.",                         "Technology"),
    ("WDC",  "Western Digital",                       "Technology"),
    ("ZBRA", "Zebra Technologies",                    "Technology"),
    # 通信服务
    ("CHTR", "Charter Communications",                "Communication Services"),
    ("CMCSA","Comcast",                               "Communication Services"),
    ("DIS",  "Walt Disney Company (The)",             "Communication Services"),
    ("EA",   "Electronic Arts",                       "Communication Services"),
    ("FOX",  "Fox Corporation (Class B)",             "Communication Services"),
    ("FOXA", "Fox Corporation (Class A)",             "Communication Services"),
    ("GOOG", "Alphabet Inc. (Class C)",               "Communication Services"),
    ("GOOGL","Alphabet Inc. (Class A)",               "Communication Services"),
    ("LYV",  "Live Nation Entertainment",             "Communication Services"),
    ("META", "Meta Platforms",                        "Communication Services"),
    ("NFLX", "Netflix",                               "Communication Services"),
    ("NWS",  "News Corp (Class B)",                   "Communication Services"),
    ("NWSA", "News Corp (Class A)",                   "Communication Services"),
    ("OMC",  "Omnicom Group",                         "Communication Services"),
    ("PSKY", "Paramount Skydance Corporation",        "Communication Services"),
    ("SATS", "EchoStar",                              "Communication Services"),
    ("T",    "AT&T",                                  "Communication Services"),
    ("TKO",  "TKO Group Holdings",                    "Communication Services"),
    ("TMUS", "T-Mobile US",                           "Communication Services"),
    ("TTD",  "Trade Desk (The)",                      "Communication Services"),
    ("TTWO", "Take-Two Interactive",                  "Communication Services"),
    ("VZ",   "Verizon",                               "Communication Services"),
    ("WBD",  "Warner Bros. Discovery",                "Communication Services"),
    # 可选消费
    ("ABNB", "Airbnb",                                "Consumer Discretionary"),
    ("AMZN", "Amazon",                                "Consumer Discretionary"),
    ("APTV", "Aptiv",                                 "Consumer Discretionary"),
    ("AZO",  "AutoZone",                              "Consumer Discretionary"),
    ("BBY",  "Best Buy",                              "Consumer Discretionary"),
    ("BKNG", "Booking Holdings",                      "Consumer Discretionary"),
    ("CCL",  "Carnival Corporation",                  "Consumer Discretionary"),
    ("CMG",  "Chipotle Mexican Grill",                "Consumer Discretionary"),
    ("CVNA", "Carvana",                               "Consumer Discretionary"),
    ("DASH", "DoorDash",                              "Consumer Discretionary"),
    ("DECK", "Deckers Brands",                        "Consumer Discretionary"),
    ("DHI",  "D. R. Horton",                          "Consumer Discretionary"),
    ("DPZ",  "Domino's",                              "Consumer Discretionary"),
    ("DRI",  "Darden Restaurants",                    "Consumer Discretionary"),
    ("EBAY", "eBay Inc.",                             "Consumer Discretionary"),
    ("EXPE", "Expedia Group",                         "Consumer Discretionary"),
    ("F",    "Ford Motor Company",                    "Consumer Discretionary"),
    ("GM",   "General Motors",                        "Consumer Discretionary"),
    ("GPC",  "Genuine Parts Company",                 "Consumer Discretionary"),
    ("GRMN", "Garmin",                                "Consumer Discretionary"),
    ("HAS",  "Hasbro",                                "Consumer Discretionary"),
    ("HD",   "Home Depot (The)",                      "Consumer Discretionary"),
    ("HLT",  "Hilton Worldwide",                      "Consumer Discretionary"),
    ("LEN",  "Lennar",                                "Consumer Discretionary"),
    ("LOW",  "Lowe's",                                "Consumer Discretionary"),
    ("LULU", "Lululemon Athletica",                   "Consumer Discretionary"),
    ("LVS",  "Las Vegas Sands",                       "Consumer Discretionary"),
    ("MAR",  "Marriott International",                "Consumer Discretionary"),
    ("MCD",  "McDonald's",                            "Consumer Discretionary"),
    ("MGM",  "MGM Resorts",                           "Consumer Discretionary"),
    ("NCLH", "Norwegian Cruise Line Holdings",        "Consumer Discretionary"),
    ("NKE",  "Nike, Inc.",                            "Consumer Discretionary"),
    ("NVR",  "NVR, Inc.",                             "Consumer Discretionary"),
    ("ORLY", "O’Reilly Automotive",                   "Consumer Discretionary"),
    ("PHM",  "PulteGroup",                            "Consumer Discretionary"),
    ("POOL", "Pool Corporation",                      "Consumer Discretionary"),
    ("RCL",  "Royal Caribbean Group",                 "Consumer Discretionary"),
    ("RL",   "Ralph Lauren Corporation",              "Consumer Discretionary"),
    ("ROST", "Ross Stores",                           "Consumer Discretionary"),
    ("SBUX", "Starbucks",                             "Consumer Discretionary"),
    ("TJX",  "TJX Companies",                         "Consumer Discretionary"),
    ("TPR",  "Tapestry, Inc.",                        "Consumer Discretionary"),
    ("TSCO", "Tractor Supply",                        "Consumer Discretionary"),
    ("TSLA", "Tesla, Inc.",                           "Consumer Discretionary"),
    ("ULTA", "Ulta Beauty",                           "Consumer Discretionary"),
    ("WSM",  "Williams-Sonoma, Inc.",                 "Consumer Discretionary"),
    ("WYNN", "Wynn Resorts",                          "Consumer Discretionary"),
    ("YUM",  "Yum! Brands",                           "Consumer Discretionary"),
    # 必需消费
    ("ADM",  "Archer Daniels Midland",                "Consumer Staples"),
    ("BF-B", "Brown–Forman",                          "Consumer Staples"),
    ("BG",   "Bunge Global",                          "Consumer Staples"),
    ("CAG",  "Conagra Brands",                        "Consumer Staples"),
    ("CASY", "Casey's",                               "Consumer Staples"),
    ("CHD",  "Church & Dwight",                       "Consumer Staples"),
    ("CL",   "Colgate-Palmolive",                     "Consumer Staples"),
    ("CLX",  "Clorox",                                "Consumer Staples"),
    ("COST", "Costco",                                "Consumer Staples"),
    ("CPB",  "Campbell's Company (The)",              "Consumer Staples"),
    ("DG",   "Dollar General",                        "Consumer Staples"),
    ("DLTR", "Dollar Tree",                           "Consumer Staples"),
    ("EL",   "Estée Lauder Companies (The)",          "Consumer Staples"),
    ("GIS",  "General Mills",                         "Consumer Staples"),
    ("HRL",  "Hormel Foods",                          "Consumer Staples"),
    ("HSY",  "Hershey Company (The)",                 "Consumer Staples"),
    ("KDP",  "Keurig Dr Pepper",                      "Consumer Staples"),
    ("KHC",  "Kraft Heinz",                           "Consumer Staples"),
    ("KMB",  "Kimberly-Clark",                        "Consumer Staples"),
    ("KO",   "Coca-Cola Company (The)",               "Consumer Staples"),
    ("KR",   "Kroger",                                "Consumer Staples"),
    ("KVUE", "Kenvue",                                "Consumer Staples"),
    ("MDLZ", "Mondelez International",                "Consumer Staples"),
    ("MKC",  "McCormick & Company",                   "Consumer Staples"),
    ("MNST", "Monster Beverage",                      "Consumer Staples"),
    ("MO",   "Altria",                                "Consumer Staples"),
    ("PEP",  "PepsiCo",                               "Consumer Staples"),
    ("PG",   "Procter & Gamble",                      "Consumer Staples"),
    ("PM",   "Philip Morris International",           "Consumer Staples"),
    ("SJM",  "J.M. Smucker Company (The)",            "Consumer Staples"),
    ("STZ",  "Constellation Brands",                  "Consumer Staples"),
    ("SYY",  "Sysco",                                 "Consumer Staples"),
    ("TAP",  "Molson Coors Beverage Company",         "Consumer Staples"),
    ("TGT",  "Target Corporation",                    "Consumer Staples"),
    ("TSN",  "Tyson Foods",                           "Consumer Staples"),
    ("WMT",  "Walmart",                               "Consumer Staples"),
    # 金融
    ("ACGL", "Arch Capital Group",                    "Financials"),
    ("AFL",  "Aflac",                                 "Financials"),
    ("AIG",  "American International Group",          "Financials"),
    ("AIZ",  "Assurant",                              "Financials"),
    ("AJG",  "Arthur J. Gallagher & Co.",             "Financials"),
    ("ALL",  "Allstate",                              "Financials"),
    ("AMP",  "Ameriprise Financial",                  "Financials"),
    ("AON",  "Aon plc",                               "Financials"),
    ("APO",  "Apollo Global Management",              "Financials"),
    ("ARES", "Ares Management",                       "Financials"),
    ("AXP",  "American Express",                      "Financials"),
    ("BAC",  "Bank of America",                       "Financials"),
    ("BEN",  "Franklin Resources",                    "Financials"),
    ("BLK",  "BlackRock",                             "Financials"),
    ("BNY",  "BNY Mellon",                            "Financials"),
    ("BRK-B","Berkshire Hathaway",                    "Financials"),
    ("BRO",  "Brown & Brown",                         "Financials"),
    ("BX",   "Blackstone Inc.",                       "Financials"),
    ("C",    "Citigroup",                             "Financials"),
    ("CB",   "Chubb Limited",                         "Financials"),
    ("CBOE", "Cboe Global Markets",                   "Financials"),
    ("CFG",  "Citizens Financial Group",              "Financials"),
    ("CINF", "Cincinnati Financial",                  "Financials"),
    ("CME",  "CME Group",                             "Financials"),
    ("COF",  "Capital One",                           "Financials"),
    ("COIN", "Coinbase",                              "Financials"),
    ("CPAY", "Corpay",                                "Financials"),
    ("EG",   "Everest Group",                         "Financials"),
    ("ERIE", "Erie Indemnity",                        "Financials"),
    ("FDS",  "FactSet",                               "Financials"),
    ("FIS",  "Fidelity National Information Services","Financials"),
    ("FISV", "Fiserv",                                "Financials"),
    ("FITB", "Fifth Third Bancorp",                   "Financials"),
    ("GL",   "Globe Life",                            "Financials"),
    ("GPN",  "Global Payments",                       "Financials"),
    ("GS",   "Goldman Sachs",                         "Financials"),
    ("HBAN", "Huntington Bancshares",                 "Financials"),
    ("HIG",  "Hartford (The)",                        "Financials"),
    ("HOOD", "Robinhood Markets",                     "Financials"),
    ("IBKR", "Interactive Brokers",                   "Financials"),
    ("ICE",  "Intercontinental Exchange",             "Financials"),
    ("IVZ",  "Invesco",                               "Financials"),
    ("JKHY", "Jack Henry & Associates",               "Financials"),
    ("JPM",  "JPMorgan Chase",                        "Financials"),
    ("KEY",  "KeyCorp",                               "Financials"),
    ("KKR",  "KKR & Co.",                             "Financials"),
    ("L",    "Loews Corporation",                     "Financials"),
    ("MA",   "Mastercard",                            "Financials"),
    ("MCO",  "Moody's Corporation",                   "Financials"),
    ("MET",  "MetLife",                               "Financials"),
    ("MRSH", "Marsh McLennan",                        "Financials"),
    ("MS",   "Morgan Stanley",                        "Financials"),
    ("MSCI", "MSCI Inc.",                             "Financials"),
    ("MTB",  "M&T Bank",                              "Financials"),
    ("NDAQ", "Nasdaq, Inc.",                          "Financials"),
    ("NTRS", "Northern Trust",                        "Financials"),
    ("PFG",  "Principal Financial Group",             "Financials"),
    ("PGR",  "Progressive Corporation",               "Financials"),
    ("PNC",  "PNC Financial Services",                "Financials"),
    ("PRU",  "Prudential Financial",                  "Financials"),
    ("PYPL", "PayPal",                                "Financials"),
    ("RF",   "Regions Financial Corporation",         "Financials"),
    ("RJF",  "Raymond James Financial",               "Financials"),
    ("SCHW", "Charles Schwab Corporation",            "Financials"),
    ("SPGI", "S&P Global",                            "Financials"),
    ("STT",  "State Street Corporation",              "Financials"),
    ("SYF",  "Synchrony Financial",                   "Financials"),
    ("TFC",  "Truist Financial",                      "Financials"),
    ("TROW", "T. Rowe Price",                         "Financials"),
    ("TRV",  "Travelers Companies (The)",             "Financials"),
    ("USB",  "U.S. Bancorp",                          "Financials"),
    ("V",    "Visa Inc.",                             "Financials"),
    ("WFC",  "Wells Fargo",                           "Financials"),
    ("WRB",  "W. R. Berkley Corporation",             "Financials"),
    ("WTW",  "Willis Towers Watson",                  "Financials"),
    ("XYZ",  "Block, Inc.",                           "Financials"),
    # 医疗健康
    ("A",    "Agilent Technologies",                  "Health Care"),
    ("ABBV", "AbbVie",                                "Health Care"),
    ("ABT",  "Abbott Laboratories",                   "Health Care"),
    ("ALGN", "Align Technology",                      "Health Care"),
    ("AMGN", "Amgen",                                 "Health Care"),
    ("BAX",  "Baxter International",                  "Health Care"),
    ("BDX",  "Becton Dickinson",                      "Health Care"),
    ("BIIB", "Biogen",                                "Health Care"),
    ("BMY",  "Bristol Myers Squibb",                  "Health Care"),
    ("BSX",  "Boston Scientific",                     "Health Care"),
    ("CAH",  "Cardinal Health",                       "Health Care"),
    ("CI",   "Cigna",                                 "Health Care"),
    ("CNC",  "Centene Corporation",                   "Health Care"),
    ("COO",  "Cooper Companies (The)",                "Health Care"),
    ("COR",  "Cencora",                               "Health Care"),
    ("CRL",  "Charles River Laboratories",            "Health Care"),
    ("CVS",  "CVS Health",                            "Health Care"),
    ("DGX",  "Quest Diagnostics",                     "Health Care"),
    ("DHR",  "Danaher Corporation",                   "Health Care"),
    ("DVA",  "DaVita",                                "Health Care"),
    ("DXCM", "Dexcom",                                "Health Care"),
    ("ELV",  "Elevance Health",                       "Health Care"),
    ("EW",   "Edwards Lifesciences",                  "Health Care"),
    ("GEHC", "GE HealthCare",                         "Health Care"),
    ("GILD", "Gilead Sciences",                       "Health Care"),
    ("HCA",  "HCA Healthcare",                        "Health Care"),
    ("HSIC", "Henry Schein",                          "Health Care"),
    ("HUM",  "Humana",                                "Health Care"),
    ("IDXX", "Idexx Laboratories",                    "Health Care"),
    ("INCY", "Incyte",                                "Health Care"),
    ("IQV",  "IQVIA",                                 "Health Care"),
    ("ISRG", "Intuitive Surgical",                    "Health Care"),
    ("JNJ",  "Johnson & Johnson",                     "Health Care"),
    ("LH",   "Labcorp",                               "Health Care"),
    ("LLY",  "Lilly (Eli)",                           "Health Care"),
    ("MCK",  "McKesson Corporation",                  "Health Care"),
    ("MDT",  "Medtronic",                             "Health Care"),
    ("MRK",  "Merck & Co.",                           "Health Care"),
    ("MRNA", "Moderna",                               "Health Care"),
    ("MTD",  "Mettler Toledo",                        "Health Care"),
    ("PFE",  "Pfizer",                                "Health Care"),
    ("PODD", "Insulet Corporation",                   "Health Care"),
    ("REGN", "Regeneron Pharmaceuticals",             "Health Care"),
    ("RMD",  "ResMed",                                "Health Care"),
    ("RVTY", "Revvity",                               "Health Care"),
    ("SOLV", "Solventum",                             "Health Care"),
    ("STE",  "Steris",                                "Health Care"),
    ("SYK",  "Stryker Corporation",                   "Health Care"),
    ("TECH", "Bio-Techne",                            "Health Care"),
    ("TMO",  "Thermo Fisher Scientific",              "Health Care"),
    ("UHS",  "Universal Health Services",             "Health Care"),
    ("UNH",  "UnitedHealth Group",                    "Health Care"),
    ("VEEV", "Veeva Systems",                         "Health Care"),
    ("VRTX", "Vertex Pharmaceuticals",                "Health Care"),
    ("VTRS", "Viatris",                               "Health Care"),
    ("WAT",  "Waters Corporation",                    "Health Care"),
    ("WST",  "West Pharmaceutical Services",          "Health Care"),
    ("ZBH",  "Zimmer Biomet",                         "Health Care"),
    ("ZTS",  "Zoetis",                                "Health Care"),
    # 工业
    ("ADP",  "Automatic Data Processing",             "Industrials"),
    ("ALLE", "Allegion",                              "Industrials"),
    ("AME",  "Ametek",                                "Industrials"),
    ("AOS",  "A. O. Smith",                           "Industrials"),
    ("AXON", "Axon Enterprise",                       "Industrials"),
    ("BA",   "Boeing",                                "Industrials"),
    ("BLDR", "Builders FirstSource",                  "Industrials"),
    ("BR",   "Broadridge Financial Solutions",        "Industrials"),
    ("CARR", "Carrier Global",                        "Industrials"),
    ("CAT",  "Caterpillar Inc.",                      "Industrials"),
    ("CHRW", "C.H. Robinson",                         "Industrials"),
    ("CMI",  "Cummins",                               "Industrials"),
    ("CPRT", "Copart",                                "Industrials"),
    ("CSX",  "CSX Corporation",                       "Industrials"),
    ("CTAS", "Cintas",                                "Industrials"),
    ("DAL",  "Delta Air Lines",                       "Industrials"),
    ("DE",   "Deere & Company",                       "Industrials"),
    ("DOV",  "Dover Corporation",                     "Industrials"),
    ("EFX",  "Equifax",                               "Industrials"),
    ("EME",  "Emcor",                                 "Industrials"),
    ("EMR",  "Emerson Electric",                      "Industrials"),
    ("ETN",  "Eaton Corporation",                     "Industrials"),
    ("EXPD", "Expeditors International",              "Industrials"),
    ("FAST", "Fastenal",                              "Industrials"),
    ("FDX",  "FedEx",                                 "Industrials"),
    ("FDXF", "FedEx Freight",                         "Industrials"),
    ("FIX",  "Comfort Systems USA",                   "Industrials"),
    ("FTV",  "Fortive",                               "Industrials"),
    ("GD",   "General Dynamics",                      "Industrials"),
    ("GE",   "GE Aerospace",                          "Industrials"),
    ("GEV",  "GE Vernova",                            "Industrials"),
    ("GNRC", "Generac",                               "Industrials"),
    ("GWW",  "W. W. Grainger",                        "Industrials"),
    ("HII",  "Huntington Ingalls Industries",         "Industrials"),
    ("HON",  "Honeywell",                             "Industrials"),
    ("HUBB", "Hubbell Incorporated",                  "Industrials"),
    ("HWM",  "Howmet Aerospace",                      "Industrials"),
    ("IEX",  "IDEX Corporation",                      "Industrials"),
    ("IR",   "Ingersoll Rand",                        "Industrials"),
    ("ITW",  "Illinois Tool Works",                   "Industrials"),
    ("J",    "Jacobs Solutions",                      "Industrials"),
    ("JBHT", "J.B. Hunt",                             "Industrials"),
    ("JCI",  "Johnson Controls",                      "Industrials"),
    ("LDOS", "Leidos",                                "Industrials"),
    ("LHX",  "L3Harris",                              "Industrials"),
    ("LII",  "Lennox International",                  "Industrials"),
    ("LMT",  "Lockheed Martin",                       "Industrials"),
    ("LUV",  "Southwest Airlines",                    "Industrials"),
    ("MAS",  "Masco",                                 "Industrials"),
    ("MMM",  "3M",                                    "Industrials"),
    ("NDSN", "Nordson Corporation",                   "Industrials"),
    ("NOC",  "Northrop Grumman",                      "Industrials"),
    ("NSC",  "Norfolk Southern",                      "Industrials"),
    ("ODFL", "Old Dominion",                          "Industrials"),
    ("OTIS", "Otis Worldwide",                        "Industrials"),
    ("PAYX", "Paychex",                               "Industrials"),
    ("PCAR", "Paccar",                                "Industrials"),
    ("PH",   "Parker Hannifin",                       "Industrials"),
    ("PNR",  "Pentair",                               "Industrials"),
    ("PWR",  "Quanta Services",                       "Industrials"),
    ("ROK",  "Rockwell Automation",                   "Industrials"),
    ("ROL",  "Rollins, Inc.",                         "Industrials"),
    ("RSG",  "Republic Services",                     "Industrials"),
    ("RTX",  "RTX Corporation",                       "Industrials"),
    ("SNA",  "Snap-on",                               "Industrials"),
    ("SWK",  "Stanley Black & Decker",                "Industrials"),
    ("TDG",  "TransDigm Group",                       "Industrials"),
    ("TT",   "Trane Technologies",                    "Industrials"),
    ("TXT",  "Textron",                               "Industrials"),
    ("UAL",  "United Airlines Holdings",              "Industrials"),
    ("UBER", "Uber",                                  "Industrials"),
    ("UNP",  "Union Pacific Corporation",             "Industrials"),
    ("UPS",  "United Parcel Service",                 "Industrials"),
    ("URI",  "United Rentals",                        "Industrials"),
    ("VLTO", "Veralto",                               "Industrials"),
    ("VRSK", "Verisk Analytics",                      "Industrials"),
    ("VRT",  "Vertiv",                                "Industrials"),
    ("WAB",  "Wabtec",                                "Industrials"),
    ("WM",   "Waste Management",                      "Industrials"),
    ("XYL",  "Xylem Inc.",                            "Industrials"),
    # 能源
    ("APA",  "APA Corporation",                       "Energy"),
    ("BKR",  "Baker Hughes",                          "Energy"),
    ("COP",  "ConocoPhillips",                        "Energy"),
    ("CVX",  "Chevron Corporation",                   "Energy"),
    ("DVN",  "Devon Energy",                          "Energy"),
    ("EOG",  "EOG Resources",                         "Energy"),
    ("EQT",  "EQT Corporation",                       "Energy"),
    ("EXE",  "Expand Energy",                         "Energy"),
    ("FANG", "Diamondback Energy",                    "Energy"),
    ("HAL",  "Halliburton",                           "Energy"),
    ("KMI",  "Kinder Morgan",                         "Energy"),
    ("MPC",  "Marathon Petroleum",                    "Energy"),
    ("OKE",  "Oneok",                                 "Energy"),
    ("OXY",  "Occidental Petroleum",                  "Energy"),
    ("PSX",  "Phillips 66",                           "Energy"),
    ("SLB",  "Schlumberger",                          "Energy"),
    ("TPL",  "Texas Pacific Land Corporation",        "Energy"),
    ("TRGP", "Targa Resources",                       "Energy"),
    ("VLO",  "Valero Energy",                         "Energy"),
    ("WMB",  "Williams Companies",                    "Energy"),
    ("XOM",  "ExxonMobil",                            "Energy"),
    # 材料
    ("ALB",  "Albemarle Corporation",                 "Materials"),
    ("AMCR", "Amcor",                                 "Materials"),
    ("APD",  "Air Products",                          "Materials"),
    ("AVY",  "Avery Dennison",                        "Materials"),
    ("BALL", "Ball Corporation",                      "Materials"),
    ("CF",   "CF Industries",                         "Materials"),
    ("CRH",  "CRH plc",                               "Materials"),
    ("CTVA", "Corteva",                               "Materials"),
    ("DD",   "DuPont",                                "Materials"),
    ("DOW",  "Dow Inc.",                              "Materials"),
    ("ECL",  "Ecolab",                                "Materials"),
    ("FCX",  "Freeport-McMoRan",                      "Materials"),
    ("IFF",  "International Flavors & Fragrances",    "Materials"),
    ("IP",   "International Paper",                   "Materials"),
    ("LIN",  "Linde plc",                             "Materials"),
    ("LYB",  "LyondellBasell",                        "Materials"),
    ("MLM",  "Martin Marietta Materials",             "Materials"),
    ("MOS",  "Mosaic Company (The)",                  "Materials"),
    ("NEM",  "Newmont",                               "Materials"),
    ("NUE",  "Nucor",                                 "Materials"),
    ("PKG",  "Packaging Corporation of America",      "Materials"),
    ("PPG",  "PPG Industries",                        "Materials"),
    ("SHW",  "Sherwin-Williams",                      "Materials"),
    ("STLD", "Steel Dynamics",                        "Materials"),
    ("SW",   "Smurfit Westrock",                      "Materials"),
    ("VMC",  "Vulcan Materials Company",              "Materials"),
    # 房地产
    ("AMT",  "American Tower",                        "Real Estate"),
    ("ARE",  "Alexandria Real Estate Equities",       "Real Estate"),
    ("AVB",  "AvalonBay Communities",                 "Real Estate"),
    ("BXP",  "BXP, Inc.",                             "Real Estate"),
    ("CBRE", "CBRE Group",                            "Real Estate"),
    ("CCI",  "Crown Castle",                          "Real Estate"),
    ("CPT",  "Camden Property Trust",                 "Real Estate"),
    ("CSGP", "CoStar Group",                          "Real Estate"),
    ("DLR",  "Digital Realty",                        "Real Estate"),
    ("DOC",  "Healthpeak Properties",                 "Real Estate"),
    ("EQIX", "Equinix",                               "Real Estate"),
    ("EQR",  "Equity Residential",                    "Real Estate"),
    ("ESS",  "Essex Property Trust",                  "Real Estate"),
    ("EXR",  "Extra Space Storage",                   "Real Estate"),
    ("FRT",  "Federal Realty Investment Trust",       "Real Estate"),
    ("HST",  "Host Hotels & Resorts",                 "Real Estate"),
    ("INVH", "Invitation Homes",                      "Real Estate"),
    ("IRM",  "Iron Mountain",                         "Real Estate"),
    ("KIM",  "Kimco Realty",                          "Real Estate"),
    ("MAA",  "Mid-America Apartment Communities",     "Real Estate"),
    ("O",    "Realty Income",                         "Real Estate"),
    ("PLD",  "Prologis",                              "Real Estate"),
    ("PSA",  "Public Storage",                        "Real Estate"),
    ("REG",  "Regency Centers",                       "Real Estate"),
    ("SBAC", "SBA Communications",                    "Real Estate"),
    ("SPG",  "Simon Property Group",                  "Real Estate"),
    ("UDR",  "UDR, Inc.",                             "Real Estate"),
    ("VICI", "Vici Properties",                       "Real Estate"),
    ("VTR",  "Ventas",                                "Real Estate"),
    ("WELL", "Welltower",                             "Real Estate"),
    ("WY",   "Weyerhaeuser",                          "Real Estate"),
    # 公用事业
    ("AEE",  "Ameren",                                "Utilities"),
    ("AEP",  "American Electric Power",               "Utilities"),
    ("AES",  "AES Corporation",                       "Utilities"),
    ("ATO",  "Atmos Energy",                          "Utilities"),
    ("AWK",  "American Water Works",                  "Utilities"),
    ("CEG",  "Constellation Energy",                  "Utilities"),
    ("CMS",  "CMS Energy",                            "Utilities"),
    ("CNP",  "CenterPoint Energy",                    "Utilities"),
    ("D",    "Dominion Energy",                       "Utilities"),
    ("DTE",  "DTE Energy",                            "Utilities"),
    ("DUK",  "Duke Energy",                           "Utilities"),
    ("ED",   "Consolidated Edison",                   "Utilities"),
    ("EIX",  "Edison International",                  "Utilities"),
    ("ES",   "Eversource Energy",                     "Utilities"),
    ("ETR",  "Entergy",                               "Utilities"),
    ("EVRG", "Evergy",                                "Utilities"),
    ("EXC",  "Exelon",                                "Utilities"),
    ("FE",   "FirstEnergy",                           "Utilities"),
    ("LNT",  "Alliant Energy",                        "Utilities"),
    ("NEE",  "NextEra Energy",                        "Utilities"),
    ("NI",   "NiSource",                              "Utilities"),
    ("NRG",  "NRG Energy",                            "Utilities"),
    ("PCG",  "PG&E Corporation",                      "Utilities"),
    ("PEG",  "Public Service Enterprise Group",       "Utilities"),
    ("PNW",  "Pinnacle West Capital",                 "Utilities"),
    ("PPL",  "PPL Corporation",                       "Utilities"),
    ("SO",   "Southern Company",                      "Utilities"),
    ("SRE",  "Sempra",                                "Utilities"),
    ("VST",  "Vistra Corp.",                          "Utilities"),
    ("WEC",  "WEC Energy Group",                      "Utilities"),
    ("XEL",  "Xcel Energy",                           "Utilities"),
]


def _fallback_sp500() -> list[dict]:
    return [
        {"symbol": sym, "name": name, "sector": sector}
        for sym, name, sector in _FALLBACK_SP500
    ]


async def _fetch_sp500_via_article(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        _WIKI_SP500_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_sp500_article_http_error", status=resp.status_code)
        return []
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, resp.text
    )


async def _fetch_sp500_via_api(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        _WIKI_SP500_API_URL, headers=_WIKI_HEADERS, timeout=20, follow_redirects=True
    )
    if resp.status_code != 200:
        logger.warning("wiki_sp500_api_http_error", status=resp.status_code)
        return []
    html = resp.json().get("parse", {}).get("text", "")
    if not html:
        return []
    return await asyncio.get_event_loop().run_in_executor(
        None, _parse_wiki_html, html
    )


async def _fetch_sp500_constituents(client: httpx.AsyncClient) -> list[dict]:
    """从 Wikipedia 动态拉取标普 500 成分股，失败时降级兜底列表."""
    sources = (
        ("article", _fetch_sp500_via_article),
        ("api", _fetch_sp500_via_api),
    )
    for source_name, fetcher in sources:
        for attempt in range(1, _WIKI_RETRIES + 1):
            try:
                constituents = await fetcher(client)
                if len(constituents) >= 450:
                    logger.info(
                        "wiki_sp500_fetched",
                        count=len(constituents),
                        source=source_name,
                        attempt=attempt,
                    )
                    return constituents
                if constituents:
                    logger.warning(
                        "wiki_sp500_too_few",
                        count=len(constituents),
                        source=source_name,
                        attempt=attempt,
                    )
            except Exception as e:
                logger.warning(
                    "wiki_sp500_fetch_failed",
                    error=str(e),
                    source=source_name,
                    attempt=attempt,
                )
            if attempt < _WIKI_RETRIES:
                await asyncio.sleep(2 ** attempt)

    logger.warning("sp500_constituent_using_fallback_list")
    return _fallback_sp500()


async def compute_sp500_upgrades() -> SP500UpgradesResponse:
    """拉取标普 500 成分股，筛选目标价三层单调递增的股票."""
    async with httpx.AsyncClient(timeout=30) as client:
        constituents = await _fetch_sp500_constituents(client)

        name_map = {c["symbol"]: c.get("name", c["symbol"]) for c in constituents}
        sector_map = {c["symbol"]: c.get("sector", "") for c in constituents}
        symbols = list(name_map.keys())

        sem = asyncio.Semaphore(_CONCURRENCY)

        async def fetch_one(sym: str) -> tuple[str, dict | None]:
            async with sem:
                return sym, await _fetch_summary(client, sym)

        results = await asyncio.gather(*[fetch_one(s) for s in symbols])

    stocks: list[UpgradeStock] = []
    for sym, summary in results:
        if not summary or not _is_monotonic_up(summary):
            continue

        m = summary["lastMonthAvgPriceTarget"]
        q = summary["lastQuarterAvgPriceTarget"]
        y = summary["lastYearAvgPriceTarget"]
        at = summary.get("allTimeAvgPriceTarget") or 0

        stocks.append(UpgradeStock(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sector_map.get(sym, ""),
            last_month_target=round(m, 2),
            last_quarter_target=round(q, 2),
            last_year_target=round(y, 2),
            all_time_target=round(at, 2),
            last_month_count=summary.get("lastMonthCount") or 0,
            month_mom=_pct(m, q),
            quarter_yoy=_pct(q, y),
            year_vs_all=_pct(y, at) if at else 0.0,
        ))

    stocks.sort(key=lambda s: s.month_mom, reverse=True)

    if stocks:
        cutoff_18m = date.today() - timedelta(days=548)
        sem2 = asyncio.Semaphore(10)
        async with httpx.AsyncClient(timeout=30) as client2:
            history_pairs = await asyncio.gather(
                *[_compute_recent_points(client2, s.symbol, sem2, cutoff_18m) for s in stocks]
            )
        history_map = dict(history_pairs)
        for stock in stocks:
            stock.recent_points = history_map.get(stock.symbol, [])

    logger.info(
        "sp500_upgrades_computed",
        total=len(constituents),
        qualifying=len(stocks),
    )

    return SP500UpgradesResponse(
        as_of=date.today().isoformat(),
        total_constituents=len(constituents),
        upgrade_count=len(stocks),
        stocks=stocks,
    )
