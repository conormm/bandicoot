"""
Contains tools for processing files (reading and writing csv and json files).
"""

from __future__ import with_statement, division

from .core import User, Record, Position, Recharge
from .helper.tools import OrderedDict, percent_overlapping_calls, percent_records_missing_location, antennas_missing_locations, warning_str
from .helper.stops import find_natural_antennas
from .utils import flatten

from datetime import datetime
from json import dumps
from collections import Counter
import time
import csv
import os


def to_csv(objects, filename, digits=5):
    """
    Export the flatten indicators of one or several users to CSV.

    Parameters
    ----------
    objects : list
        List of objects to be exported.
    filename : string
        File to export to.
    digits : int
        Precision of floats.

    Examples
    --------
    This function can be used to export the results of
    :meth`bandicoot.utils.all`.
    >>> U_1 = bc.User()
    >>> U_2 = bc.User()
    >>> bc.to_csv([bc.utils.all(U_1), bc.utils.all(U_2)], 'results_1_2.csv')

    If you only have one object, you can simply pass it as argument:
    >>> bc.to_csv(bc.utils.all(U_1), 'results_1.csv')
    """

    if not isinstance(objects, list):
        objects = [objects]

    data = [flatten(obj) for obj in objects]
    all_keys = [d for datum in data for d in datum.keys()]
    field_names = sorted(set(all_keys), key=lambda x: all_keys.index(x))

    with open(filename, 'wb') as f:
        w = csv.writer(f)
        w.writerow(field_names)

        def make_repr(item):
            if item is None:
                return None
            elif isinstance(item, float):
                return repr(round(item, digits))
            else:
                return str(item)

        for row in data:
            row = dict((k, make_repr(v)) for k, v in row.items())
            w.writerow([make_repr(row.get(k, None)) for k in field_names])

    print "Successfully exported %d object(s) to %s" % (len(objects), filename)


def to_json(objects, filename):
    """
    Export the indicators of one or several users to JSON.

    Parameters
    ----------
    objects : list
        List of objects to be exported.
    filename : string
        File to export to.

    Examples
    --------
    This function can be use to export the results of
    :meth`bandicoot.utils.all`.
    >>> U_1 = bc.User()
    >>> U_2 = bc.User()
    >>> bc.to_json([bc.utils.all(U_1), bc.utils.all(U_2)], 'results_1_2.json')

    If you only have one object, you can simply pass it as argument:
    >>> bc.to_json(bc.utils.all(U_1), 'results_1.json')
    """

    if not isinstance(objects, list):
        objects = [objects]

    obj_dict = {obj['name']: obj for obj in objects}

    with open(filename, 'wb') as f:
        f.write(dumps(obj_dict, indent=4, separators=(',', ': ')))
    print "Successfully exported %d object(s) to %s" % (len(objects), filename)


def _tryto(function, argument, **kwargs):
    try:
        return function(argument)
    except:
        if 'default' in kwargs:
            return kwargs['default']
        else:
            # We catch exceptions later to count incorrect records
            # and which fields are incorrect
            return ValueError


def _parse_record(data, duration_format='seconds'):
    """
    Parse a raw data dictionary and return a Record object.
    """

    def _map_duration(s):
        if s == '':
            return None
        elif duration_format.lower() == 'seconds':
            return int(s)
        else:
            t = time.strptime(s, duration_format)
            return 3600 * t.tm_hour + 60 * t.tm_min + t.tm_sec

    def _map_position(data):
        antenna = Position()

        if 'antenna_id' in data and data['antenna_id']:
            antenna.antenna = data['antenna_id']

        if 'place_id' in data:
            raise NameError("Use field name 'antenna_id' in input files. "
                            "'place_id' is deprecated.")

        if 'latitude' in data and 'longitude' in data:
            latitude = data['latitude']
            longitude = data['longitude']
            # latitude and longitude should not be empty strings.
            if latitude and longitude:
                antenna.location = float(latitude), float(longitude)

        return antenna

    return Record(interaction=data['interaction'] if data['interaction'] else None,
                  direction=data['direction'],
                  correspondent_id=data['correspondent_id'],
                  datetime=_tryto(lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"), data['datetime']),
                  call_duration=_tryto(_map_duration, data['call_duration']),
                  position=_tryto(_map_position, data))


def _parse_recharge(data):
    dt = _tryto(lambda x: datetime.strptime(x, "%Y-%m-%d"),
                data['datetime'])

    return Recharge(datetime=dt,
                    amount=_tryto(float, data.get('amount'), default=0),
                    retailer_id=data.get('retailer_id'))


def filter_record(records):
    """
    Filter records and remove items with missing or inconsistent fields

    Parameters
    ----------

    records : list
        A list of Record objects

    Returns
    -------
    records, ignored : (Record list, dict)
        A tuple of filtered records, and a dictionary counting the
        missings fields

    """

    def scheme(r):
        return {
            'interaction': r.interaction in ['call', 'text', None],
            'direction': r.interaction is None or r.direction in ['in', 'out'],
            'correspondent_id': r.interaction is None or r.correspondent_id is not None,
            'datetime': isinstance(r.datetime, datetime),
            'call_duration': r.interaction is None or (isinstance(r.call_duration, (int, float)) if r.interaction == 'call' else True),
            'location': r.interaction is not None or r.position.type() is not None
        }

    ignored = OrderedDict([
        ('all', 0),
        ('interaction', 0),
        ('direction', 0),
        ('correspondent_id', 0),
        ('datetime', 0),
        ('call_duration', 0),
        ('location', 0),
    ])

    bad_records = []

    def _filter(records):
        for r in records:
            valid = True
            for key, valid_key in scheme(r).iteritems():
                if not valid_key:
                    ignored[key] += 1
                    bad_records.append(r)
                    # Not breaking, to count all fields with errors
                    valid = False

            if valid:
                yield r
            else:
                ignored['all'] += 1

    return list(_filter(records)), ignored, bad_records


def load(name, records, antennas, attributes=None, recharges=None,
         antennas_path=None, attributes_path=None, recharges_path=None,
         describe=False, warnings=False, drop_duplicates=False):
    """
    Creates a new user. This function is used by read_csv, read_orange,
    and read_telenor. If you want to implement your own reader function,
    we advise you to use the load() function

    `load` will output warnings on the standard output if some records or
    antennas are missing a position.

    Parameters
    ----------

    name : str
        The name of the user. It is stored in User.name and is useful when
        exporting metrics about multiple users.

    records: list
        A list or a generator of Record objects.

    antennas : dict
        A dictionary of the position for each antenna.

    attributes : dict
        A (key,value) dictionary of attributes for the current user

    describe : boolean
        If describe is True, it will print a description of the loaded user
        to the standard output. Defaults to false.

    warnings : boolean, default True
        If warnings is equal to False, the function will not output the
        warnings on the standard output.

    drop_duplicates : boolean, default False
        If drop_duplicates is equal to True, the function will remove
        duplicated records.

    For instance:

    .. code-block:: python

       >>> records = [Record(...),...]
       >>> antennas = {'A51': (37.245265, 115.803418),...}
       >>> attributes = {'age': 60}
       >>> load("Frodo", records, antennas, attributes)

    will returns a new User object.
    """

    user = User()
    user.name = name
    user.antennas_path = antennas_path
    user.attributes_path = attributes_path
    user.recharges_path = recharges_path

    user.records, ignored, bad_records = filter_record(records)

    w = []  # List of all warnings to keep code clean

    if ignored['all'] != 0:
        w += ["Warning: {} record(s) were removed due to "
              "missing or incomplete fields.".format(ignored['all'])]

        for k in ignored.keys():
            if k != 'all' and ignored[k] != 0:
                w += [" " * 9 + "%s: %i record(s) with "
                      "incomplete values" % (k, ignored[k])]

    user.ignored_records = dict(ignored)

    if antennas is not None:
        user.antennas = antennas
    if attributes is not None:
        user.attributes = attributes
    if recharges is not None:
        user.recharges = recharges

    if not user.has_attributes and user.attributes_path is not None:
        w += ["Warning: Attributes path {} is given, but no "
              "attributes are loaded.".format(attributes_path)]

    if not user.has_recharges and user.recharges_path is not None:
        w += ["Warning: Recharges path {} is given, but no "
              "recharges are loaded.".format(recharges_path)]

    percent_missing = percent_records_missing_location(user)
    if percent_missing > 0:
        w += ["Warning: {0:.2%} of the records are missing "
              "a location.".format(percent_missing)]

        if antennas is None:
            w += [" " * 9 + "No antennas file was given and "
                  "records are using antennas for position."]

    msg_loc = antennas_missing_locations(user)
    if msg_loc > 0:
        w += ["Warning: {} antenna(s) are missing a location.".format(msg_loc)]

    pct_overlap_calls = percent_overlapping_calls(user.records, 300)
    if pct_overlap_calls > 0:
        w += ["Warning: {0:.2%} of calls overlap the next call by more than " +
              "5 minutes.".format(pct_overlap_calls)]

    sorted_min_records = sorted(set(user.records), key=lambda r: r.datetime)
    num_dup = len(user.records) - len(sorted_min_records)
    if num_dup > 0:
        if drop_duplicates:
            w += ["Warning: {0:d} duplicated record(s) were removed.".format(num_dup)]
            user.records = sorted_min_records
        else:
            w += ["Warning: {0:d} record(s) are duplicated.".format(num_dup)]

    if describe:
        user.describe()

    if warnings:
        for message in w:
            print(warning_str(message))

    return user, bad_records


def _read_network(user, records_path, attributes_path, read_function,
                  antennas_path=None, extension=".csv"):
    connections = {}
    correspondents = Counter([r.correspondent_id for r in user.records])

    # Try to load all the possible correspondent files
    for c_id, count in sorted(correspondents.items()):
        correspondent_file = os.path.join(records_path, c_id + extension)
        if os.path.exists(correspondent_file):
            connections[c_id] = read_function(c_id, records_path,
                                              antennas_path, attributes_path,
                                              describe=False, network=False,
                                              warnings=False)
        else:
            connections[c_id] = None

    def _is_consistent(record):
        if record.correspondent_id == user.name:
            correspondent = user
        elif record.correspondent_id in connections:
            correspondent = connections[record.correspondent_id]
        else:
            return True  # consistent by default

        return correspondent is None or record.has_match(correspondent.records)

    def all_user_iter():
        if user.name not in connections:
            yield user

        for u in connections.values():
            if u is not None:
                yield u

    # Filter records and count total number of records before/after
    num_total_records = sum(len(u.records) for u in all_user_iter())
    for u in all_user_iter():
        u.records = filter(_is_consistent, u.records)
    num_total_records_filtered = sum(len(u.records) for u in all_user_iter())

    # Report non reciprocated records
    nb_inconsistent = num_total_records - num_total_records_filtered
    if nb_inconsistent > 0:
        pct_inconsistent = nb_inconsistent / num_total_records
        print warning_str("Warning: {} records ({:.2%}) for all users in the "
                          "network were not reciprocated. They have been "
                          "removed.".format(nb_inconsistent, pct_inconsistent))

    # Return the network dictionary sorted by key
    return OrderedDict(sorted(connections.items(), key=lambda t: t[0]))


def _load_attributes(path):
    try:
        with open(path, 'rb') as csv_file:
            reader = csv.DictReader(csv_file)
            return dict((d['key'], d['value']) for d in reader)
    except IOError:
        return None


def _load_recharges(path):
    try:
        with open(path, 'rb') as csv_file:
            reader = csv.DictReader(csv_file)
            return map(_parse_recharge, reader)
    except IOError:
        return None


def read_csv(user_id, records_path, antennas_path=None, attributes_path=None,
             recharges_path=None, network=False, duration_format='seconds',
             describe=True, warnings=True, errors=False):
    """
    Load user records from a CSV file.

    Parameters
    ----------

    user_id : str
        ID of the user (filename)

    records_path : str
        Path of the directory all the user files.

    antennas_path : str, optional
        Path of the CSV file containing (place_id, latitude, longitude) values.
        This allows antennas to be mapped to their locations.

    recharges_path : str, optional
        Path of the directory containing recharges files
        (``datetime, amount, balance, retailer_id`` CSV file).

    antennas_path : str, optional
        Path of the CSV file containing (place_id, latitude, longitude) values.
        This allows antennas to be mapped to their locations.

    network : bool, optional
        If network is True, bandicoot loads the network of the user's
        correspondants from the same path. Defaults to False.

    duration_format : str, default is 'seconds'
        Allows reading records with call duration specified in other formats
        than seconds. Options are 'seconds' or any format such as '%H:%M:%S',
        '%M%S', etc.

    describe : boolean
        If describe is True, it will print a description of the loaded user
        to the standard output.

    errors : boolean
        If errors is True, returns a tuple (user, errors), where user is the
        user object and errors are the records which could not be loaded.


    Examples
    --------

    >>> user = bandicoot.read_csv('sample_records', '.')
    >>> print len(user.records)
    10

    >>> user = bandicoot.read_csv('sample_records', 'samples', sample_places.csv')
    >>> print len(user.antennas)
    5

    >>> user = bandicoot.read_csv('sample_records', '.', None, 'sample_attributes.csv')
    >>> print user.attributes['age']
    25

    Notes
    -----
    - The csv files can be single, or double quoted if needed.
    - Empty cells are filled with ``None``. For example, if the column
      ``call_duration`` is empty for one record, its value will be ``None``.
      Other values such as ``"N/A"``, ``"None"``, ``"null"`` will be
      considered as a text.
    """

    antennas = None
    if antennas_path is not None:
        try:
            with open(antennas_path, 'rb') as csv_file:
                reader = csv.DictReader(csv_file)
                antennas = dict((d['antenna_id'], (float(d['latitude']),
                                                   float(d['longitude'])))
                                for d in reader)
        except IOError:
            pass

    user_records = os.path.join(records_path, user_id + '.csv')
    with open(user_records, 'rb') as csv_file:
        reader = csv.DictReader(csv_file)
        records = [_parse_record(r, duration_format) for r in reader]

    attributes = None
    if attributes_path is not None:
        user_attributes = os.path.join(attributes_path, user_id + '.csv')
        attributes = _load_attributes(user_attributes)

    recharges = None
    if recharges_path is not None:
        user_recharges = os.path.join(recharges_path, user_id + '.csv')
        recharges = _load_recharges(user_recharges)

    user, bad_records = load(user_id, records, antennas, attributes, recharges,
                             antennas_path, attributes_path, recharges_path,
                             describe=False, warnings=warnings)

    # Loads the network
    if network is True:
        user.network = _read_network(user, records_path, attributes_path,
                                     read_csv, antennas_path)
        user.recompute_missing_neighbors()

    if describe:
        user.describe()

    if errors:
        return user, bad_records
    return user


def read_orange(user_id, records_path, antennas_path=None,
                attributes_path=None, recharges_path=None, network=False,
                describe=True, warnings=True, errors=False):
    """
    Load user records from a CSV file in *orange* format:

    ``call_record_type;basic_service;user_msisdn;call_partner_identity;datetime;call_duration;longitude;latitude``

    ``basic_service`` takes one of the following values:

    - 11: telephony;
    - 12: emergency calls;
    - 21: short message (in)
    - 22: short message (out)

    Parameters
    ----------
    user_id : str
        ID of the user (filename)

    records_path : str
        Path of the directory all the user files.

    antennas_path : str, optional
        Path of the CSV file containing (antenna_id, latitude, longitude)
        values. This allows antennas to be mapped to their locations.

    attributes_path : str, optional
        Path of the directory containing attributes files (``key, value`` CSV
        file). Attributes can for instance be variables such as like, age, or
        gender. Attributes can be helpful to compute specific metrics.

    network : bool, optional
        If network is True, bandicoot loads the network of the user's
        correspondants from the same path. Defaults to False.

    describe : boolean
        If describe is True, it will print a description of the loaded user to
        the standard output.

    errors : boolean
        If errors is True, returns a tuple (user, errors), where user is the
        user object and errors are the records which could not be loaded.
    """

    def _parse(reader):
        records = []
        antennas = dict()

        for row in reader:
            direction = 'out' if row['call_record_type'] == '1' else 'in'
            interaction = 'call' if row['basic_service'] in ['11', '12'] else 'text'
            contact = row['call_partner_identity']
            date = datetime.strptime(row['datetime'], "%Y-%m-%d %H:%M:%S")
            call_duration = float(row['call_duration']) if row['call_duration'] != "" else None
            lon, lat = float(row['longitude']), float(row['latitude'])
            latlon = (lat, lon)

            antenna = None
            for key, value in antennas.items():
                if latlon == value:
                    antenna = key
                    break
            if antenna is None:
                antenna = len(antennas) + 1
                antennas[antenna] = latlon

            position = Position(antenna=antenna, location=latlon)

            record = Record(direction=direction,
                            interaction=interaction,
                            correspondent_id=contact,
                            call_duration=call_duration,
                            datetime=date,
                            position=position)
            records.append(record)

        return records, antennas

    user_records = os.path.join(records_path, user_id + ".csv")
    fields = ['call_record_type', 'basic_service', 'user_msisdn',
              'call_partner_identity', 'datetime', 'call_duration',
              'longitude', 'latitude']

    with open(user_records, 'rb') as f:
        reader = csv.DictReader(f, delimiter=";", fieldnames=fields)
        records, antennas = _parse(reader)

    attributes = None
    if attributes_path is not None:
        user_attributes = os.path.join(attributes_path, user_id + '.csv')
        attributes = _load_attributes(user_attributes)

    recharges = None
    if recharges_path is not None:
        user_recharges = os.path.join(recharges_path, user_id + '.csv')
        recharges = _load_recharges(user_recharges)

    user, bad_records = load(user_id, records, antennas, attributes, recharges,
                             antennas_path, attributes_path, recharges_path,
                             describe=False, warnings=warnings)

    if network is True:
        user.network = _read_network(user, records_path, attributes_path,
                                     read_orange, antennas_path)
        user.recompute_missing_neighbors()

    if describe:
        user.describe()

    if errors:
        return user, bad_records
    return user


def read_combined_csv_gps(user, records_path, warnings=True, errors=False, **kwargs):
    """
    Load records from a CSV file containing call, text, and location interactions.
    """
    user = read_csv(user, records_path, warnings=warnings, errors=errors, **kwargs)

    location_records = filter(lambda r: r.position.type() is 'gps', user.records)
    antennas, get_antenna_id = find_natural_antennas(location_records)

    for r in user.records:
        r.position = Position(antenna=get_antenna_id(r.datetime, error=time))

    user.antennas.update(antennas)

    return user


def read_telenor(incoming_cdr, outgoing_cdr, cell_towers, describe=True,
                 warnings=True):
    """
    Load user records from a CSV file in *telenor* format, which is only
    applicable for call records.

        .. note:: read_telenor has been deprecated in bandicoot 0.4.

    Arguments
    ---------
    incoming_cdr: str
        Path to the CSV file containing incoming records, using the following
        scheme: ::

             B_PARTY,A_PARTY,DURATION,B_CELL,CALL_DATE,CALL_TIME,CALL_TYPE

    outgoing_cdr: str
        Path to the CSV file containing outgoing records, using the following
        scheme: ::

             A_NUMBER,B_NUMBER,DURATION,B_CELL,CALL_DATE,CALL_TIME,CALL_TYPE

    cell_towers: str
        Path to the CSV file containing the positions of all

    describe : boolean
        If describe is True, it will print a description of the loaded user to
        the standard output.

    """

    print warning_str("read_telenor has been deprecated in bandicoot 0.4.")

    import itertools
    import csv

    def parse_direction(code):
        if code == 'MOC':
            return 'out'
        elif code == 'MTC':
            return 'in'
        else:
            raise NotImplementedError

    cells = None
    with open(cell_towers, 'rb') as f:
        cell_towers_list = csv.DictReader(f)
        cells = {}
        for line in cell_towers_list:
            if line['LONGITUDE'] != '' and line['LATITUDE'] != '':
                latlon = (float(line['LONGITUDE']), float(line['LATITUDE']))
                cell_id = line['CELLID_HEX']
                cells[cell_id] = latlon

    def parse_record(raw):
        direction = parse_direction(raw['CALL_TYPE'].strip())

        if direction == 'in':
            contact = raw.get('A_PARTY', raw.get('A_NUMBER'))
            cell_id = raw['B_CELL']
        else:
            contact = raw.get('B_PARTY', raw.get('B_NUMBER'))
            cell_id = raw['A_CELL']

        position = Position(antenna=cell_id, location=cells.get(cell_id))

        _date_str = raw.get('CDATE', raw.get('CALL_DATE'))
        _time_str = raw.get('CTIME', raw.get('CALL_TIME'))
        _datetime = datetime.strptime(_date_str + _time_str,
                                      "%Y%m%d%H:%M:%S")

        r = Record(interaction='call',
                   direction=direction,
                   correspondent_id=contact,
                   call_duration=float(raw['DURATION'].strip()),
                   datetime=_datetime,
                   position=position)

        return r

    with open(incoming_cdr, 'rb') as f_in:
        incoming_ = map(parse_record, csv.DictReader(f_in))

        with open(outgoing_cdr, 'rb') as f:
            outgoing_ = map(parse_record, csv.DictReader(f))

            records = itertools.chain(incoming_, outgoing_)

    name = incoming_cdr

    user, errors = load(name, records, cells, warnings=None, describe=False)

    if describe:
        user.describe()

    return user
