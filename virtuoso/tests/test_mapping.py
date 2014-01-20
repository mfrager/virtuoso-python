from nose.plugins.skip import SkipTest

from sqlalchemy.engine import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker, mapper, relation
from sqlalchemy.sql import text, bindparam
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey

from rdflib import URIRef, Graph
from rdflib.namespace import Namespace, NamespaceManager

from virtuoso.vmapping import *
from virtuoso.vstore import Virtuoso

engine = create_engine("virtuoso://dba:dba@VOS")
Session = sessionmaker(bind=engine)
session = Session(autocommit=False)
metadata = MetaData()

TST = Namespace('http://example.com/test#')
nsm = NamespaceManager(Graph())
nsm.bind('tst', TST)
nsm.bind('virtrdf', VirtRDF)

ta_iri = PatternIriClass(TST.ta_iri,'http://example.com/test#tA/%d', None, ('id', Integer, False))
tb_iri = PatternIriClass(TST.tb_iri,'http://example.com/test#tB/%d', None, ('id', Integer, False))

test_table = Table('test_table', metadata,
                   Column('id', Integer, primary_key=True),
                   Column('name', String),
                   schema="test.DBA",
                   )


class Object(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

test_table_a = Table("test_a", metadata,
                     Column("id", Integer, primary_key=True,
                            info={'rdf': IriSubjectQuadMapPattern(ta_iri)}),
                     Column('name', String,
                            info={'rdf': LiteralQuadMapPattern(TST.name)}),
                     schema="test.DBA",
                     info={"rdf_class":TST.tA})
test_table_b = Table("test_b", metadata,
                     Column("id", Integer, primary_key=True,
                            info={'rdf': IriSubjectQuadMapPattern(tb_iri)}),
                     Column('name', String,
                            info={'rdf': LiteralQuadMapPattern(TST.name)}),
                     Column("a_id", Integer, ForeignKey(test_table_a.c.id),
                            info={'rdf': IriQuadMapPattern(ta_iri, TST.alink)}),
                     schema="test.DBA",
                     info={"rdf_class":TST.tB})
test_table_c = Table("test_c", metadata,
                     Column("id", Integer, primary_key=True, autoincrement=False),
                     Column('name', String),
                     schema="test.DBA")


class A(Object):
    pass


class B(Object):
    pass


def table_exists(table):
    conn = engine.connect()
    catalog, schema = table.schema.split('.', 1) if table.schema else (None, None)
    result = conn.execute(
        text("SELECT TABLE_NAME FROM TABLES WHERE "
             "lower(TABLE_CATALOG) = lower(:catname) AND "
             "lower(TABLE_SCHEMA) = lower(:schemaname) AND "
             "lower(TABLE_NAME) = lower(:tablename)"),
        tablename = table.name, schemaname=schema, catname=catalog)
    return result.scalar() is not None


def clean():
    for table in ("test_table", "test_b", "test_a", "test_c"):
        conn = engine.connect()
        result = conn.execute(
            text("SELECT TABLE_CATALOG FROM TABLES WHERE "
                 "lower(TABLE_NAME) = '%s'" % table)
        )
        for s in result.fetchall():
            conn.execute(text("DROP TABLE %s..%s" % (s[0], table)))
            session.commit()

class TestMapping(object):
    @classmethod
    def setup_class(cls):
        clean()
        test_table_a.create(engine)
        test_table_b.create(engine)
        A.__mapper__=mapper(A, test_table_a)
        B.__mapper__=mapper(B, test_table_b, properties={'a': relation(A)})

    @classmethod
    def teardown_class(self):
        clean()

    def test_05_declare_quads(self):
        ap=ClassQuadMapPattern(A)
        bp=ClassQuadMapPattern(B)
        g=GraphQuadMapPattern(TST.g, None, None, None, ap, bp)
        qs = QuadStorage(TST.qs, [g])
        defn = qs.definition_statement(nsm)
        print defn
        r = session.execute('sparql '+defn)
        #for x in r.fetchall(): print x
        a = A()
        b = B()
        b.a = a
        session.add(b)
        session.commit()
        store = Virtuoso("DSN=VOS;UID=dba;PWD=dba;WideAsUTF16=Y", quad_storage=qs.name)

        graph = Graph(store, identifier=TST.g)
        assert list(graph.triples((None, TST.alink, None)))
