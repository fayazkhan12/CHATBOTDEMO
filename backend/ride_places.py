"""Places a rider can name without typing a full address: airports, railway stations, bus stands and the
landmarks people actually say ("Hawa Mahal", "Sindhi Camp"). Coordinates are to about 100 m, which is
plenty for a demo fare and a map pin; the live destination search of the hotel supplier is used for
everything not listed here.

Each city: (name, vehicle-plate prefix, centre lat, centre lng, [aliases])
Each place: (name, kind, lat, lng, [aliases])  kind: airport | station | bus | landmark | area | mall
"""
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from ride_engine import haversine_km
except ImportError:  # started as backend.server
    from backend.ride_engine import haversine_km

CITIES: Dict[str, Tuple[str, float, float, List[str]]] = {
    "Delhi": ("DL1C", 28.6139, 77.2090, ["new delhi", "ncr"]),
    "Mumbai": ("MH02", 19.0760, 72.8777, ["bombay"]),
    "Bengaluru": ("KA01", 12.9716, 77.5946, ["bangalore", "blr"]),
    "Hyderabad": ("TS09", 17.3850, 78.4867, ["hyd"]),
    "Chennai": ("TN09", 13.0827, 80.2707, ["madras"]),
    "Kolkata": ("WB02", 22.5726, 88.3639, ["calcutta"]),
    "Pune": ("MH12", 18.5204, 73.8567, ["poona"]),
    "Ahmedabad": ("GJ01", 23.0225, 72.5714, ["amdavad"]),
    "Jaipur": ("RJ14", 26.9124, 75.7873, ["pink city"]),
    "Udaipur": ("RJ27", 24.5854, 73.7125, []),
    "Jodhpur": ("RJ19", 26.2389, 73.0243, []),
    "Jaisalmer": ("RJ15", 26.9157, 70.9083, []),
    "Goa": ("GA07", 15.4909, 73.8278, ["panaji", "panjim"]),
    "Lucknow": ("UP32", 26.8467, 80.9462, []),
    "Varanasi": ("UP65", 25.3176, 82.9739, ["banaras", "benares", "kashi"]),
    "Agra": ("UP80", 27.1767, 78.0081, []),
    "Chandigarh": ("CH01", 30.7333, 76.7794, []),
    "Amritsar": ("PB02", 31.6340, 74.8723, []),
    "Kochi": ("KL07", 9.9312, 76.2673, ["cochin", "ernakulam"]),
    "Mysuru": ("KA09", 12.2958, 76.6394, ["mysore"]),
    "Bhopal": ("MP04", 23.2599, 77.4126, []),
    "Indore": ("MP09", 22.7196, 75.8577, []),
    "Nagpur": ("MH31", 21.1458, 79.0882, []),
    "Patna": ("BR01", 25.5941, 85.1376, []),
    "Bhubaneswar": ("OD02", 20.2961, 85.8245, []),
    "Visakhapatnam": ("AP31", 17.6868, 83.2185, ["vizag"]),
    "Surat": ("GJ05", 21.1702, 72.8311, []),
    "Guwahati": ("AS01", 26.1445, 91.7362, []),
    "Dehradun": ("UK07", 30.3165, 78.0322, []),
    "Rishikesh": ("UK14", 30.0869, 78.2676, []),
    "Haridwar": ("UK08", 29.9457, 78.1642, []),
    "Manali": ("HP01", 32.2396, 77.1887, []),
    "Srinagar": ("JK01", 34.0837, 74.7973, []),
    "Leh": ("LA01", 34.1526, 77.5771, ["ladakh"]),
}

P = List[Tuple[str, str, float, float, List[str]]]
PLACES: Dict[str, P] = {
    "Delhi": [
        ("Indira Gandhi International Airport", "airport", 28.5562, 77.1000, ["delhi airport", "igi airport", "t3", "terminal 3", "del"]),
        ("New Delhi Railway Station", "station", 28.6428, 77.2197, ["ndls", "new delhi station", "paharganj"]),
        ("Old Delhi Railway Station", "station", 28.6609, 77.2278, ["delhi junction", "dli", "chandni chowk station"]),
        ("Hazrat Nizamuddin Railway Station", "station", 28.5883, 77.2540, ["nizamuddin station", "nzm"]),
        ("Anand Vihar ISBT", "bus", 28.6469, 77.3159, ["anand vihar bus stand", "anand vihar railway station"]),
        ("Kashmere Gate ISBT", "bus", 28.6676, 77.2290, ["kashmiri gate", "kashmere gate bus stand"]),
        ("Connaught Place", "area", 28.6315, 77.2167, ["cp", "rajiv chowk"]),
        ("India Gate", "landmark", 28.6129, 77.2295, []),
        ("Red Fort", "landmark", 28.6562, 77.2410, ["lal qila"]),
        ("Qutub Minar", "landmark", 28.5245, 77.1855, ["qutab minar"]),
        ("Lotus Temple", "landmark", 28.5535, 77.2588, []),
        ("Akshardham Temple", "landmark", 28.6127, 77.2773, ["akshardham"]),
        ("Select Citywalk Saket", "mall", 28.5285, 77.2190, ["saket", "citywalk"]),
        ("Hauz Khas Village", "area", 28.5494, 77.2001, ["hauz khas"]),
        ("Aerocity", "area", 28.5503, 77.1210, ["aero city"]),
    ],
    "Mumbai": [
        ("Chhatrapati Shivaji Maharaj International Airport T2", "airport", 19.0896, 72.8656, ["mumbai airport", "bom", "terminal 2", "t2"]),
        ("Mumbai Domestic Airport T1", "airport", 19.0990, 72.8680, ["santacruz airport", "terminal 1", "t1"]),
        ("Chhatrapati Shivaji Maharaj Terminus", "station", 18.9398, 72.8355, ["cst", "csmt", "vt", "victoria terminus"]),
        ("Mumbai Central Railway Station", "station", 18.9696, 72.8193, ["bct", "mumbai central"]),
        ("Lokmanya Tilak Terminus", "station", 19.0695, 72.8903, ["ltt", "kurla terminus"]),
        ("Dadar Railway Station", "station", 19.0186, 72.8424, ["dadar"]),
        ("Andheri Railway Station", "station", 19.1197, 72.8464, ["andheri"]),
        ("Bandra Railway Station", "station", 19.0544, 72.8402, ["bandra"]),
        ("Gateway of India", "landmark", 18.9220, 72.8347, ["colaba"]),
        ("Marine Drive", "landmark", 18.9439, 72.8228, []),
        ("Juhu Beach", "landmark", 19.0988, 72.8267, ["juhu"]),
        ("Bandra Kurla Complex", "area", 19.0674, 72.8700, ["bkc"]),
        ("Powai Hiranandani", "area", 19.1176, 72.9060, ["powai"]),
    ],
    "Bengaluru": [
        ("Kempegowda International Airport", "airport", 13.1986, 77.7066, ["bangalore airport", "bengaluru airport", "blr airport", "devanahalli"]),
        ("KSR Bengaluru City Junction", "station", 12.9783, 77.5726, ["majestic railway station", "bangalore city station", "sbc"]),
        ("Kempegowda Bus Station", "bus", 12.9774, 77.5726, ["majestic", "majestic bus stand", "kbs"]),
        ("Yeshwanthpur Railway Station", "station", 13.0285, 77.5409, ["yeshwantpur", "yesvantpur"]),
        ("MG Road", "area", 12.9757, 77.6065, ["mahatma gandhi road"]),
        ("Indiranagar", "area", 12.9784, 77.6408, []),
        ("Koramangala", "area", 12.9352, 77.6245, []),
        ("Whitefield", "area", 12.9698, 77.7500, []),
        ("Electronic City", "area", 12.8452, 77.6602, ["e city"]),
        ("HSR Layout", "area", 12.9116, 77.6474, ["hsr"]),
        ("Cubbon Park", "landmark", 12.9763, 77.5929, []),
        ("Lalbagh Botanical Garden", "landmark", 12.9507, 77.5848, ["lalbagh"]),
        ("Bangalore Palace", "landmark", 12.9988, 77.5921, ["bengaluru palace"]),
    ],
    "Hyderabad": [
        ("Rajiv Gandhi International Airport", "airport", 17.2403, 78.4294, ["hyderabad airport", "shamshabad", "hyd airport"]),
        ("Secunderabad Junction", "station", 17.4339, 78.5016, ["secunderabad railway station", "sc"]),
        ("Hyderabad Deccan Nampally Station", "station", 17.3910, 78.4690, ["nampally", "hyderabad station"]),
        ("Mahatma Gandhi Bus Station", "bus", 17.3786, 78.4821, ["mgbs", "imlibun"]),
        ("Jubilee Bus Station", "bus", 17.4467, 78.4972, ["jbs"]),
        ("Charminar", "landmark", 17.3616, 78.4747, []),
        ("Golconda Fort", "landmark", 17.3833, 78.4011, ["golkonda"]),
        ("HITEC City", "area", 17.4435, 78.3772, ["hi tech city", "hitech city", "madhapur"]),
        ("Banjara Hills", "area", 17.4156, 78.4347, []),
        ("Gachibowli", "area", 17.4401, 78.3489, []),
    ],
    "Chennai": [
        ("Chennai International Airport", "airport", 12.9941, 80.1709, ["chennai airport", "meenambakkam", "maa"]),
        ("Chennai Central", "station", 13.0827, 80.2707, ["mgr central", "chennai railway station"]),
        ("Chennai Egmore", "station", 13.0732, 80.2609, ["egmore"]),
        ("Koyambedu CMBT Bus Terminus", "bus", 13.0694, 80.1948, ["cmbt", "koyambedu"]),
        ("Marina Beach", "landmark", 13.0500, 80.2824, []),
        ("T Nagar", "area", 13.0418, 80.2341, ["t. nagar", "thyagaraya nagar"]),
        ("Guindy", "area", 13.0067, 80.2206, []),
        ("Adyar", "area", 13.0012, 80.2565, []),
        ("Velachery", "area", 12.9815, 80.2180, []),
    ],
    "Kolkata": [
        ("Netaji Subhas Chandra Bose International Airport", "airport", 22.6547, 88.4467, ["kolkata airport", "dum dum airport", "ccu"]),
        ("Howrah Junction", "station", 22.5839, 88.3426, ["howrah station", "howrah railway station"]),
        ("Sealdah Railway Station", "station", 22.5686, 88.3703, ["sealdah"]),
        ("Victoria Memorial", "landmark", 22.5448, 88.3426, []),
        ("Park Street", "area", 22.5535, 88.3513, []),
        ("Esplanade", "area", 22.5646, 88.3510, ["dharmatala"]),
        ("Salt Lake Sector V", "area", 22.5736, 88.4339, ["sector 5", "sector v", "salt lake"]),
    ],
    "Pune": [
        ("Pune International Airport", "airport", 18.5822, 73.9197, ["pune airport", "lohegaon", "pnq"]),
        ("Pune Junction Railway Station", "station", 18.5289, 73.8744, ["pune station", "pune railway station"]),
        ("Shivajinagar Bus Stand", "bus", 18.5308, 73.8474, ["shivajinagar", "shivaji nagar"]),
        ("Swargate Bus Stand", "bus", 18.5018, 73.8636, ["swargate"]),
        ("Shaniwar Wada", "landmark", 18.5195, 73.8553, ["shaniwarwada"]),
        ("Koregaon Park", "area", 18.5362, 73.8940, []),
        ("Hinjewadi IT Park", "area", 18.5912, 73.7389, ["hinjewadi", "hinjawadi"]),
        ("Viman Nagar", "area", 18.5679, 73.9143, []),
        ("Kothrud", "area", 18.5074, 73.8077, []),
    ],
    "Ahmedabad": [
        ("Sardar Vallabhbhai Patel International Airport", "airport", 23.0772, 72.6347, ["ahmedabad airport", "amd"]),
        ("Ahmedabad Junction Railway Station", "station", 23.0258, 72.6014, ["kalupur", "ahmedabad station", "ahmedabad railway station"]),
        ("Sabarmati Ashram", "landmark", 23.0607, 72.5800, ["gandhi ashram"]),
        ("Kankaria Lake", "landmark", 23.0067, 72.6020, ["kankaria"]),
        ("Law Garden", "area", 23.0270, 72.5560, []),
    ],
    "Jaipur": [
        ("Jaipur International Airport", "airport", 26.8242, 75.8122, ["jaipur airport", "sanganer airport", "jai"]),
        ("Jaipur Junction Railway Station", "station", 26.9196, 75.7878, ["jaipur railway station", "jaipur station", "jaipur junction", "jp", "jaipur jn"]),
        ("Sindhi Camp Bus Stand", "bus", 26.9220, 75.7940, ["sindhi camp", "jaipur bus stand", "jaipur bus station", "rsrtc bus stand"]),
        ("Hawa Mahal", "landmark", 26.9239, 75.8267, ["palace of winds"]),
        ("City Palace Jaipur", "landmark", 26.9258, 75.8237, ["city palace"]),
        ("Jantar Mantar", "landmark", 26.9247, 75.8244, []),
        ("Amber Fort", "landmark", 26.9855, 75.8513, ["amer fort", "amer"]),
        ("Nahargarh Fort", "landmark", 26.9372, 75.8155, ["nahargarh"]),
        ("Jal Mahal", "landmark", 26.9535, 75.8462, []),
        ("Albert Hall Museum", "landmark", 26.9116, 75.8195, ["albert hall"]),
        ("World Trade Park", "mall", 26.8549, 75.8083, ["wtp", "malviya nagar wtp"]),
        ("C Scheme", "area", 26.9068, 75.8030, ["c-scheme"]),
        ("Bani Park", "area", 26.9327, 75.7889, []),
        ("Vaishali Nagar", "area", 26.9136, 75.7405, []),
        ("Malviya Nagar", "area", 26.8553, 75.8202, []),
    ],
    "Udaipur": [
        ("Maharana Pratap Airport", "airport", 24.6177, 73.8961, ["udaipur airport", "dabok airport", "udr"]),
        ("Udaipur City Railway Station", "station", 24.5768, 73.7132, ["udaipur station", "udaipur railway station"]),
        ("City Palace Udaipur", "landmark", 24.5764, 73.6835, ["city palace"]),
        ("Lake Pichola", "landmark", 24.5714, 73.6797, ["pichola"]),
        ("Fateh Sagar Lake", "landmark", 24.5997, 73.6783, ["fateh sagar", "fatehsagar"]),
        ("Jagdish Temple", "landmark", 24.5801, 73.6835, []),
        ("Saheliyon Ki Bari", "landmark", 24.5990, 73.6910, []),
        ("Sajjangarh Monsoon Palace", "landmark", 24.5912, 73.6523, ["monsoon palace", "sajjangarh"]),
    ],
    "Jodhpur": [
        ("Jodhpur Airport", "airport", 26.2511, 73.0489, ["jdh"]),
        ("Jodhpur Junction Railway Station", "station", 26.2830, 73.0230, ["jodhpur station", "jodhpur railway station"]),
        ("Mehrangarh Fort", "landmark", 26.2979, 73.0187, ["mehrangarh"]),
        ("Umaid Bhawan Palace", "landmark", 26.2720, 73.0478, ["umaid bhawan"]),
        ("Clock Tower Jodhpur", "landmark", 26.2958, 73.0234, ["ghanta ghar", "sardar market"]),
    ],
    "Jaisalmer": [
        ("Jaisalmer Fort", "landmark", 26.9124, 70.9126, ["sonar quila", "golden fort"]),
        ("Sam Sand Dunes", "landmark", 26.8340, 70.5100, ["sam dunes"]),
    ],
    "Goa": [
        ("Goa Dabolim Airport", "airport", 15.3808, 73.8314, ["goa airport", "dabolim", "goi"]),
        ("Mopa Airport", "airport", 15.7440, 73.8640, ["manohar international airport", "north goa airport"]),
        ("Madgaon Railway Station", "station", 15.2760, 73.9580, ["margao station", "madgaon station", "madgaon junction"]),
        ("Panaji Kadamba Bus Stand", "bus", 15.4960, 73.8330, ["panaji bus stand", "panjim bus stand"]),
        ("Panaji", "area", 15.4909, 73.8278, ["panjim"]),
        ("Calangute Beach", "landmark", 15.5438, 73.7553, ["calangute"]),
        ("Baga Beach", "landmark", 15.5553, 73.7517, ["baga"]),
        ("Anjuna Beach", "landmark", 15.5736, 73.7406, ["anjuna"]),
        ("Candolim Beach", "landmark", 15.5180, 73.7620, ["candolim"]),
        ("Vasco da Gama", "area", 15.3982, 73.8113, ["vasco"]),
        ("Basilica of Bom Jesus", "landmark", 15.5009, 73.9116, ["old goa", "bom jesus"]),
        ("Mapusa", "area", 15.5937, 73.8089, []),
        ("Palolem Beach", "landmark", 15.0100, 74.0232, ["palolem"]),
    ],
    "Lucknow": [
        ("Chaudhary Charan Singh International Airport", "airport", 26.7606, 80.8893, ["lucknow airport", "amausi"]),
        ("Lucknow Charbagh Railway Station", "station", 26.8312, 80.9220, ["charbagh", "lucknow station", "lucknow railway station"]),
        ("Alambagh Bus Station", "bus", 26.8160, 80.9050, ["alambagh"]),
        ("Hazratganj", "area", 26.8554, 80.9462, []),
        ("Bara Imambara", "landmark", 26.8689, 80.9122, ["bada imambara"]),
    ],
    "Varanasi": [
        ("Lal Bahadur Shastri Airport", "airport", 25.4524, 82.8593, ["varanasi airport", "babatpur"]),
        ("Varanasi Junction Railway Station", "station", 25.3269, 82.9870, ["varanasi station", "varanasi railway station", "banaras station"]),
        ("Kashi Vishwanath Temple", "landmark", 25.3109, 83.0107, ["kashi vishwanath", "vishwanath mandir"]),
        ("Dashashwamedh Ghat", "landmark", 25.3070, 83.0104, ["dashashwamedh", "ganga aarti"]),
        ("Assi Ghat", "landmark", 25.2886, 83.0059, ["assi"]),
        ("Sarnath", "landmark", 25.3811, 83.0225, []),
        ("Banaras Hindu University", "landmark", 25.2677, 82.9913, ["bhu"]),
    ],
    "Agra": [
        ("Taj Mahal", "landmark", 27.1751, 78.0421, ["taj"]),
        ("Agra Fort", "landmark", 27.1795, 78.0211, []),
        ("Agra Cantt Railway Station", "station", 27.1583, 77.9889, ["agra cantt", "agra station", "agra railway station"]),
        ("Agra Airport", "airport", 27.1558, 77.9609, ["kheria airport"]),
        ("Fatehpur Sikri", "landmark", 27.0940, 77.6679, []),
    ],
    "Chandigarh": [
        ("Chandigarh International Airport", "airport", 30.6735, 76.7885, ["chandigarh airport", "mohali airport", "ixc"]),
        ("Chandigarh Railway Station", "station", 30.6928, 76.8213, ["chandigarh station"]),
        ("Sector 17 Plaza", "area", 30.7410, 76.7830, ["sector 17", "isbt 17"]),
        ("Rock Garden", "landmark", 30.7525, 76.8101, []),
        ("Sukhna Lake", "landmark", 30.7421, 76.8188, []),
    ],
    "Amritsar": [
        ("Golden Temple", "landmark", 31.6200, 74.8765, ["harmandir sahib", "darbar sahib"]),
        ("Sri Guru Ram Dass Jee International Airport", "airport", 31.7096, 74.7973, ["amritsar airport", "atq"]),
        ("Amritsar Junction Railway Station", "station", 31.6270, 74.8709, ["amritsar station", "amritsar railway station"]),
        ("Wagah Border", "landmark", 31.6044, 74.5731, ["attari wagah", "wagah"]),
    ],
    "Kochi": [
        ("Cochin International Airport", "airport", 10.1520, 76.4019, ["kochi airport", "cochin airport", "nedumbassery", "cok"]),
        ("Ernakulam Junction Railway Station", "station", 9.9696, 76.2905, ["ernakulam station", "ernakulam junction", "kochi railway station"]),
        ("Fort Kochi", "area", 9.9658, 76.2421, ["fort cochin"]),
        ("Lulu Mall Kochi", "mall", 10.0272, 76.3087, ["lulu mall"]),
        ("Marine Drive Kochi", "landmark", 9.9786, 76.2759, ["marine drive"]),
    ],
    "Mysuru": [
        ("Mysore Palace", "landmark", 12.3052, 76.6552, ["mysuru palace", "amba vilas"]),
        ("Mysuru Junction Railway Station", "station", 12.3130, 76.6441, ["mysore station", "mysore junction"]),
        ("Mysore Airport", "airport", 12.2296, 76.6558, ["mandakalli airport", "mysuru airport"]),
    ],
    "Bhopal": [
        ("Raja Bhoj Airport", "airport", 23.2875, 77.3374, ["bhopal airport", "bho"]),
        ("Bhopal Junction Railway Station", "station", 23.2662, 77.4129, ["bhopal station", "bhopal railway station"]),
    ],
    "Indore": [
        ("Devi Ahilya Bai Holkar Airport", "airport", 22.7218, 75.8011, ["indore airport", "idr"]),
        ("Indore Junction Railway Station", "station", 22.7157, 75.8668, ["indore station", "indore railway station"]),
        ("Rajwada Palace", "landmark", 22.7185, 75.8553, ["rajwada"]),
    ],
    "Nagpur": [
        ("Dr Babasaheb Ambedkar International Airport", "airport", 21.0922, 79.0472, ["nagpur airport", "nag"]),
        ("Nagpur Junction Railway Station", "station", 21.1498, 79.0872, ["nagpur station", "nagpur railway station"]),
    ],
    "Patna": [
        ("Jay Prakash Narayan Airport", "airport", 25.5913, 85.0880, ["patna airport", "pat"]),
        ("Patna Junction Railway Station", "station", 25.6027, 85.1376, ["patna station", "patna railway station"]),
    ],
    "Bhubaneswar": [
        ("Biju Patnaik International Airport", "airport", 20.2444, 85.8178, ["bhubaneswar airport", "bbi"]),
        ("Bhubaneswar Railway Station", "station", 20.2653, 85.8438, ["bhubaneswar station"]),
        ("Lingaraj Temple", "landmark", 20.2382, 85.8338, ["lingaraja"]),
    ],
    "Visakhapatnam": [
        ("Visakhapatnam Airport", "airport", 17.7212, 83.2245, ["vizag airport", "vtz"]),
        ("Visakhapatnam Junction Railway Station", "station", 17.7233, 83.2907, ["vizag station", "vizag railway station"]),
        ("RK Beach", "landmark", 17.7138, 83.3257, ["ramakrishna beach"]),
    ],
    "Surat": [
        ("Surat Airport", "airport", 21.1141, 72.7418, ["stv"]),
        ("Surat Railway Station", "station", 21.2057, 72.8409, ["surat station"]),
    ],
    "Guwahati": [
        ("Lokpriya Gopinath Bordoloi International Airport", "airport", 26.1061, 91.5859, ["guwahati airport", "gau"]),
        ("Guwahati Railway Station", "station", 26.1824, 91.7505, ["guwahati station", "pandu"]),
        ("Kamakhya Temple", "landmark", 26.1664, 91.7054, ["kamakhya"]),
    ],
    "Dehradun": [
        ("Jolly Grant Airport", "airport", 30.1897, 78.1803, ["dehradun airport", "ded"]),
        ("Dehradun Railway Station", "station", 30.3150, 78.0322, ["dehradun station"]),
        ("Clock Tower Dehradun", "landmark", 30.3244, 78.0419, ["ghanta ghar", "clock tower"]),
    ],
    "Rishikesh": [
        ("Laxman Jhula", "landmark", 30.1279, 78.3285, ["lakshman jhula"]),
        ("Ram Jhula", "landmark", 30.1195, 78.3165, []),
    ],
    "Haridwar": [
        ("Har Ki Pauri", "landmark", 29.9565, 78.1695, ["har ki paudi"]),
        ("Haridwar Junction Railway Station", "station", 29.9457, 78.1642, ["haridwar station", "haridwar railway station"]),
    ],
    "Manali": [
        ("Manali Mall Road", "area", 32.2432, 77.1892, ["mall road manali", "mall road"]),
        ("Hadimba Temple", "landmark", 32.2478, 77.1805, ["hidimba devi temple"]),
        ("Bhuntar Kullu Manali Airport", "airport", 31.8768, 77.1544, ["kullu airport", "bhuntar airport", "kuu"]),
        ("Solang Valley", "landmark", 32.3167, 77.1583, ["solang"]),
    ],
    "Srinagar": [
        ("Srinagar International Airport", "airport", 33.9871, 74.7742, ["srinagar airport", "sxr"]),
        ("Dal Lake Boulevard", "landmark", 34.0857, 74.8431, ["dal lake", "boulevard road"]),
        ("Lal Chowk", "area", 34.0721, 74.8120, []),
    ],
    "Leh": [
        ("Kushok Bakula Rimpochee Airport", "airport", 34.1359, 77.5465, ["leh airport", "ixl"]),
        ("Leh Market", "area", 34.1652, 77.5848, ["main bazaar leh"]),
    ],
}

_STOP = {"the", "a", "an", "to", "from", "in", "at", "near", "of", "me", "my", "ke", "ka", "ki", "se", "tak", "paas", "pass", "mein", "me", "pe"}
_KIND_RANK = {"airport": 0, "station": 1, "bus": 2, "landmark": 3, "area": 4, "mall": 5, "city": 6}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower().replace("&", " and ")).strip()


def _tokens(s: str) -> List[str]:
    return [t for t in _norm(s).split() if t and t not in _STOP]


def _build() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for city, (plate, lat, lng, city_aliases) in CITIES.items():
        slug = _norm(city).replace(" ", "-")
        out.append({"id": f"{slug}-centre", "name": f"{city} city centre", "city": city, "kind": "city", "lat": lat, "lng": lng, "aka": [city.lower(), *city_aliases], "plate": plate})
        for i, (name, kind, plat, plng, aka) in enumerate(PLACES.get(city, [])):
            out.append({"id": f"{slug}-{i}", "name": name, "city": city, "kind": kind, "lat": plat, "lng": plng, "aka": aka, "plate": plate})
    for p in out:
        city = p["city"]
        names = [p["name"], *p["aka"]]
        p["_city_tokens"] = set(_tokens(city) + [t for a in CITIES[city][3] for t in _tokens(a)])
        p["_forms"] = [(_norm(n), _tokens(n)) for n in names]
    return out


ALL: List[Dict[str, Any]] = _build()
BY_ID = {p["id"]: p for p in ALL}


def public(p: Dict[str, Any]) -> Dict[str, Any]:
    sub = {"airport": "Airport", "station": "Railway station", "bus": "Bus stand", "landmark": "Landmark", "area": "Area", "mall": "Mall", "city": "City centre"}[p["kind"]]
    return {"id": p["id"], "name": p["name"], "sub": f"{sub}, {p['city']}", "kind": p["kind"], "city": p["city"], "lat": p["lat"], "lng": p["lng"]}


def _score(p: Dict[str, Any], q_norm: str, q_tokens: List[str], prefer_city: str = "") -> float:
    """0 = no match. All words of the query must appear (as the start of a word) in the name, a nickname or the city."""
    if not q_tokens:
        return 0.0
    best = 0.0
    city_tokens = p["_city_tokens"]
    for form, toks in p["_forms"]:
        covered = 0
        exact = 0
        for qt in q_tokens:
            hit = [t for t in toks if t == qt]
            if hit:
                covered += 1
                exact += 1
            elif any(t.startswith(qt) for t in toks) and len(qt) >= 2:
                covered += 1
            elif qt in city_tokens or any(c.startswith(qt) for c in city_tokens if len(qt) >= 3):
                covered += 1
        if covered < len(q_tokens):
            continue
        s = 10.0 + exact * 3.0
        if form == q_norm:
            s += 40
        elif form.startswith(q_norm):
            s += 15
        elif q_norm in form:
            s += 6
        # shorter, more specific names beat long ones; "city centre" only wins when nothing else is named
        s -= min(len(toks), 8) * 0.3
        best = max(best, s)
    if best and p["kind"] == "city":
        best -= 6
    if best and prefer_city and p["city"] == prefer_city:
        best += 4
    return best


def search(q: str, limit: int = 8, prefer_city: str = "") -> List[Dict[str, Any]]:
    q_norm = _norm(q)
    toks = _tokens(q)
    scored = [(s, p) for p in ALL if (s := _score(p, q_norm, toks, prefer_city)) > 0]
    scored.sort(key=lambda sp: (-sp[0], _KIND_RANK[sp[1]["kind"]], sp[1]["name"]))
    return [p for _, p in scored[:limit]]


def resolve(q: str, prefer_city: str = "") -> Dict[str, Any]:
    """The one place the words mean, or why not: {'place': {...}} | {'ambiguous': [...]} | {}"""
    q_norm = _norm(q)
    toks = _tokens(q)
    scored = [(s, p) for p in ALL if (s := _score(p, q_norm, toks, prefer_city)) > 0]
    if not scored:
        return {}
    scored.sort(key=lambda sp: (-sp[0], _KIND_RANK[sp[1]["kind"]]))
    top = scored[0][0]
    tied = [p for s, p in scored if s >= top - 0.01]
    cities = {p["city"] for p in tied}
    names_city = any(t in tied[0]["_city_tokens"] for t in toks)
    if len(cities) > 1 and not names_city and not prefer_city:
        return {"ambiguous": [public(p) for p in tied[:5]]}
    return {"place": scored[0][1]}


def near(lat: float, lng: float, limit: int = 8, max_km: float = 40.0) -> List[Dict[str, Any]]:
    ranked = sorted(((haversine_km((lat, lng), (p["lat"], p["lng"])), p) for p in ALL if p["kind"] != "city"), key=lambda x: x[0])
    return [p for d, p in ranked[:limit] if d <= max_km]


def plate_prefix_near(lat: float, lng: float) -> str:
    best = min(CITIES.items(), key=lambda kv: haversine_km((lat, lng), (kv[1][1], kv[1][2])))
    return best[1][0]
