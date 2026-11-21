"""MongoDB persistence for the application's fixed, parameterized query dialect.

This is not a general SQL engine: identifiers and grammar are allowlisted, and
values are always BSON values, never query expressions supplied by a client.
All collections reside in MongoDB. No SQLite/PostgreSQL fallback exists.
Multi-document writes require Atlas or a replica set. Write conflicts fail closed
and are returned as retryable 503s, rather than silently losing transactions.
"""
import re
import sqlite3  # exception compatibility only, never a storage connection
import time
from functools import lru_cache

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

FIELDS = {
    'users': 'id email password role verified',
    'verification': 'token user_id expires',
    'auth_events': 'id created user_id account_key source_ip success',
    'flows': 'event_id created source_ip collector payload prediction',
    'alerts': 'id created kind user_id source_ip title evidence recommendation dedup_key status',
    'notifications': 'id created recipient subject body state attempts error next_try claim_token lease_until',
    'website_events': 'site_id event_id created occurred event_type account_key source_ip success payload_hash',
    'website_accounts': 'site_id account_key email verified updated',
    'classroom_progress': 'user_id payload',
}
FIELDS = {key: value.split() for key, value in FIELDS.items()}
DEFAULTS = {'users': {'role': 'user', 'verified': 0},
            'alerts': {'status': 'open'},
            'notifications': {'state': 'pending', 'attempts': 0, 'next_try': 0,
                              'error': None, 'claim_token': None, 'lease_until': 0}}
UNIQUE = {'users': [('id',), ('email',)], 'verification': [('token',)],
          'auth_events': [('id',)], 'flows': [('event_id',)], 'alerts': [('id',)],
          'notifications': [('id',)], 'website_events': [('site_id', 'event_id')],
          'website_accounts': [('site_id', 'account_key')], 'classroom_progress': [('user_id',)]}


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, rows=(), lastrowid=None):
        self.rows = iter(rows)
        self.lastrowid = lastrowid

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


@lru_cache(maxsize=8)
def client_for(uri):
    return MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
                       socketTimeoutMS=30000, maxPoolSize=20)


class MongoStore:
    def __init__(self, uri, name):
        self.client = client_for(uri)
        self.database = self.client[name]
        self.session = None

    def initialize(self):
        hello = self.client.admin.command('hello')
        if not hello.get('setName') and hello.get('msg') != 'isdbgrid':
            raise RuntimeError('MongoDB transactions require Atlas or a replica set; standalone MongoDB is unsupported')
        for table in FIELDS:
            for columns in UNIQUE[table]:
                self.database[table].create_index([(c, 1) for c in columns], unique=True)
        for table, fields in [('auth_events', [('account_key', 1), ('created', 1)]),
                              ('auth_events', [('source_ip', 1), ('created', 1)]),
                              ('alerts', [('dedup_key', 1), ('created', 1)]),
                              ('notifications', [('state', 1), ('next_try', 1)]),
                              ('website_events', [('site_id', 1), ('occurred', 1), ('account_key', 1)])]:
            self.database[table].create_index(fields)
        self.database['_counters'].update_one({'_id': '_write_serial'}, {'$setOnInsert': {'seq': 0}}, upsert=True)
        for table in FIELDS:
            if 'id' in FIELDS[table]:
                highest = self.database[table].find_one(sort=[('id', -1)])
                self.database['_counters'].update_one({'_id': table}, {'$max': {'seq': highest['id'] if highest else 0}}, upsert=True)

    def begin(self):
        if self.session is not None:
            return
        self.session = self.client.start_session()
        self.session.start_transaction(read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'))
        # Intentional low-volume prototype serialization: competing writes conflict.
        self.database['_counters'].update_one({'_id': '_write_serial'}, {'$inc': {'seq': 1}}, session=self.session)

    def commit(self):
        if self.session is None:
            return
        deadline = time.monotonic() + 20
        while True:
            try:
                self.session.commit_transaction()
                break
            except OperationFailure as exc:
                if exc.has_error_label('UnknownTransactionCommitResult') and time.monotonic() < deadline:
                    continue
                raise
        self.session.end_session()
        self.session = None

    def rollback(self):
        if self.session is not None:
            try:
                if self.session.in_transaction:
                    self.session.abort_transaction()
            finally:
                self.session.end_session()
                self.session = None

    close = rollback

    def execute(self, sql, params=()):
        sql = ' '.join(sql.strip().rstrip(';').split())
        values = iter(params)

        def literal(text):
            text = text.strip()
            if text == '?':
                return next(values)
            if text.upper() == 'NULL':
                return None
            if re.fullmatch(r'-?\d+(?:\.\d+)?', text):
                return float(text) if '.' in text else int(text)
            if re.fullmatch(r"'[^']*'", text):
                return text[1:-1]
            raise ValueError('Unsupported literal in internal MongoDB query')

        def field(table, name):
            if name not in FIELDS[table]:
                raise ValueError('Unknown field in internal MongoDB query')
            return name

        def where(table, clause):
            filters = []
            # BETWEEN contains its own AND; convert it before splitting conjunctions.
            pattern = r"(\w+)\s*(BETWEEN\s+\?\s+AND\s+\?|(?:>=|<=|=|>|<)\s*(?:\?|'[^']*'|-?\d+(?:\.\d+)?|NULL))(?: AND |$)"
            pos = 0
            for match in re.finditer(pattern, clause):
                if match.start() != pos:
                    raise ValueError('Unsupported internal query predicate')
                pos = match.end()
                name, expr = field(table, match[1]), match[2]
                if expr.startswith('BETWEEN'):
                    filters.append({name: {'$gte': next(values), '$lte': next(values)}})
                else:
                    op, raw = re.fullmatch(r'(>=|<=|=|>|<)\s*(.*)', expr).groups()
                    filters.append({name: {dict(zip(['=', '>', '<', '>=', '<='], ['$eq', '$gt', '$lt', '$gte', '$lte']))[op]: literal(raw)}})
            if pos != len(clause):
                raise ValueError('Unsupported internal query predicate')
            return {'$and': filters} if filters else {}

        if sql == 'BEGIN IMMEDIATE':
            self.begin()
            return Result()
        if sql.startswith(('CREATE TABLE IF NOT EXISTS ', 'CREATE INDEX IF NOT EXISTS ')):
            # Index/schema initialization is centralized in initialize(), not SQL DDL.
            return Result()
        match = re.fullmatch(r'SELECT (.+?) FROM (\w+)(?: WHERE (.*?))?(?: ORDER BY (\w+)(?: (DESC|ASC))?)?(?: LIMIT (\?|\d+))?', sql)
        if match:
            projection, table, clause, order, direction, limit = match.groups()
            if table not in FIELDS:
                raise ValueError('Unknown collection')
            query = where(table, clause or '')
            collection = self.database[table]
            kw = {'session': self.session}
            if projection == 'COUNT(*)':
                result = Result([Row(count=collection.count_documents(query, **kw))])
            elif projection.startswith('COUNT(DISTINCT '):
                name = field(table, projection[15:-1])
                rows = list(collection.aggregate([{'$match': query}, {'$group': {'_id': '$'+name}}, {'$count': 'count'}], **kw))
                result = Result([Row(count=rows[0]['count'] if rows else 0)])
            elif projection.startswith('MAX('):
                name = field(table, projection[4:-1])
                row = collection.find_one(query, sort=[(name, -1)], **kw)
                result = Result([Row(max=row.get(name) if row else None)])
            else:
                names = FIELDS[table] if projection == '*' else [field(table, n.strip()) for n in projection.split(',')]
                cursor = collection.find(query, {'_id': 0}, **kw)
                if order:
                    cursor = cursor.sort(field(table, order), -1 if direction == 'DESC' else 1)
                if limit:
                    cursor = cursor.limit(int(literal(limit)))
                result = Result([Row((n, row.get(n)) for n in names) for row in cursor])
        else:
            self.begin()
            kw = {'session': self.session}
            match = re.fullmatch(r'INSERT INTO (\w+)(?:\(([^)]+)\))? VALUES\(([^)]+)\)(.*)', sql)
            try:
                if match:
                    table, names, raw, suffix = match.groups()
                    names = [n.strip() for n in names.split(',')] if names else FIELDS[table]
                    document = {field(table, n): literal(v) for n, v in zip(names, raw.split(','), strict=True)}
                    document = DEFAULTS.get(table, {}) | document
                    if suffix:
                        if table not in ('classroom_progress', 'website_accounts') or 'ON CONFLICT' not in suffix:
                            raise ValueError('Unsupported upsert')
                        keys = UNIQUE[table][0]
                        query = {key: document[key] for key in keys}
                        old = self.database[table].find_one(query, **kw)
                        if table != 'website_accounts' or not old or document['updated'] >= old['updated']:
                            self.database[table].update_one(query, {'$set': document}, upsert=True, **kw)
                    else:
                        if 'id' in FIELDS[table] and 'id' not in document:
                            counter = self.database['_counters'].find_one_and_update({'_id': table}, {'$inc': {'seq': 1}}, return_document=ReturnDocument.AFTER, **kw)
                            if not counter:
                                raise RuntimeError('Run manage.py init-db before using the app')
                            document['id'] = counter['seq']
                        self.database[table].insert_one(document, **kw)
                    result = Result(lastrowid=document.get('id'))
                elif match := re.fullmatch(r'UPDATE (\w+) SET (.+?) WHERE (.+)', sql):
                    table, assignments, clause = match.groups()
                    sets, inc = {}, {}
                    for assignment in assignments.split(','):
                        name, raw = assignment.split('=', 1)
                        name = field(table, name.strip())
                        if raw.strip() == name + '+1':
                            inc[name] = 1
                        else:
                            sets[name] = literal(raw)
                    query = where(table, clause)
                    update = ({'$set': sets} if sets else {}) | ({'$inc': inc} if inc else {})
                    self.database[table].update_many(query, update, **kw)
                    result = Result()
                elif match := re.fullmatch(r'DELETE FROM (\w+) WHERE (.+)', sql):
                    table, clause = match.groups()
                    self.database[table].delete_many(where(table, clause), **kw)
                    result = Result()
                else:
                    raise ValueError('Unsupported internal MongoDB query')
            except DuplicateKeyError as exc:
                raise sqlite3.IntegrityError('Database constraint failed') from exc
        sentinel = object()
        if next(values, sentinel) is not sentinel:
            raise ValueError('Unused query parameters')
        return result
