import pandas as pd
import sqlite3
from trade_logic.utils import okunur_date_yap
from schemas import *
from trade_logic.utils import integer_date_yap


class SqlLite_Service:
    def __init__(self, _config):
        self.conn = None
        self._config = _config
        self.db = _config.get("coin")
        self.conn = self.get_conn()
        self._tablo_yoksa_olustur()

    def get_conn(self):
        if self.conn:
            return self.conn
        self.conn = sqlite3.connect(f'./coindata/{self.db}.db')
        return self.conn

    def schemayi_query_texte_cevir(self, schema):
        _query = []
        for el in schema:
            _query.append(f'{el["name"]} {el["type"]} {el["primary"]}')

        return ', '.join(_query)

    def _tablo_yoksa_olustur(self):
        tip = self._config.get('pencere')
        swing_tip = self._config.get('swing_pencere')
        coin = self._config.get('coin')

        candles = f'{coin}_{tip}'
        swing_candles = f'{coin}_{swing_tip}'
        islemler = f'islemler_{coin}_{tip}'
        prophet_tahminler = f'prophet_{coin}_{tip}'
        trader = f'trader_{coin}_{tip}'

        self.get_conn().cursor().execute(
            f'CREATE TABLE IF NOT EXISTS {candles}({self.schemayi_query_texte_cevir(mum_schema)});'
        )
        self.get_conn().cursor().execute(
            f'CREATE TABLE IF NOT EXISTS {swing_candles}({self.schemayi_query_texte_cevir(mum_schema)});'
        )
        self.get_conn().cursor().execute(
            f'CREATE TABLE IF NOT EXISTS {islemler}({self.schemayi_query_texte_cevir(islem_schema)});'
        )
        self.get_conn().cursor().execute(
            f'CREATE TABLE IF NOT EXISTS {prophet_tahminler}({self.schemayi_query_texte_cevir(prophet_tahmin_schema)});'
        )
        self.get_conn().cursor().execute(
            f'CREATE TABLE IF NOT EXISTS {trader}({self.schemayi_query_texte_cevir(trader_schema)});'
        )
        self.get_conn().commit()

    def mum_datasi_yukle(self, tip, prophet_service, baslangic_gunu, bitis_gunu):
        coin = self._config.get('coin')
        data = prophet_service.tg_binance_service.get_client().get_historical_klines(
            symbol=coin, interval=tip,
            start_str=str(baslangic_gunu), end_str=str(bitis_gunu), limit=500
        )
        data = self.veri_listesi_olustur(data)
        _query = f"""INSERT INTO {f'{coin}_{tip}'} {self.values_ifadesi_olustur(mum_schema)}
                ON CONFLICT({mum_schema[0]["name"]}) {self.update_ifadesi_olustur(mum_schema)};"""

        self.get_conn().cursor().executemany(_query, data)
        self.get_conn().commit()
        print(f'API-dan yukleme tamamlandi {coin}_{tip} {str(baslangic_gunu)} {str(bitis_gunu)}')

    @staticmethod
    def veri_listesi_olustur(tempdata):
        data = []
        for i in range(len(tempdata)):
            row = (int(tempdata[i][0]), okunur_date_yap(tempdata[i][0]), float(tempdata[i][1]),
                   float(tempdata[i][2]), float(tempdata[i][3]),
                   float(tempdata[i][4]), float(tempdata[i][5])
                   )
            data.append(row)
        return data

    @staticmethod
    def values_ifadesi_olustur(_schema):
        soru_isaretleri = ', '.join("?" for el in _schema)
        return f"VALUES({soru_isaretleri})"

    @staticmethod
    def update_ifadesi_olustur(_schema):
        guncelle = ', '.join(f'{el["name"]}=excluded.{el["name"]}' for el in _schema)
        return f"DO UPDATE SET {guncelle}"

    def veri_yaz(self, data, _type):
        coin = self._config.get('coin')
        tip = self._config.get('pencere')
        data = [str(integer_date_yap(data['ds']))] + [str(el) for el in data.values()]
        if _type == "tahmin":
            _query = f"""INSERT INTO {f'prophet_{coin}_{tip}'} {self.values_ifadesi_olustur(prophet_tahmin_schema)}
                ON CONFLICT({prophet_tahmin_schema[0]["name"]}) {self.update_ifadesi_olustur(prophet_tahmin_schema)};"""
        elif _type == "islem":
            _query = f"""INSERT INTO islemler_{coin}_{tip} {self.values_ifadesi_olustur(islem_schema)}
                            ON CONFLICT({islem_schema[0]["name"]}) {self.update_ifadesi_olustur(islem_schema)};"""
        elif _type == "trader":
            _query = f"""INSERT INTO trader_{coin}_{tip} {self.values_ifadesi_olustur(trader_schema)}
                            ON CONFLICT({trader_schema[0]["name"]}) {self.update_ifadesi_olustur(trader_schema)};"""

        self.get_conn().cursor().executemany(_query, [data])
        self.get_conn().commit()
        print(f'------->    {_type} yazildi {coin}_{tip} ')

    def islemleri_temizle(self):
        coin = self._config.get('coin')
        tip = self._config.get('pencere')
        _query = f"DELETE FROM islemler_{coin}_{tip};"
        self.get_conn().cursor().execute(_query)
        self.get_conn().commit()

    def veri_getir(self, coin, pencere, _type, baslangic=None, bitis=None):
        schema = None
        if _type == 'prophet':
            query = f'SELECT * FROM prophet_{coin}_{pencere}'
            schema = prophet_tahmin_schema
        elif _type == 'mum':
            query = f"""SELECT * FROM {f'{coin}_{pencere}'}
                    WHERE open_ts_int < {int(bitis.timestamp())*1000}"""
            schema = mum_schema
        elif _type == 'islem':
            query = f"""SELECT * FROM islemler_{coin}_{pencere}"""
            schema = islem_schema
        elif _type == 'trader':
            query = f"""SELECT * FROM trader_{coin}_{pencere}"""
            schema = trader_schema
        curr = self.get_conn().cursor().execute(query)
        data = curr.fetchall()
        main_dataframe = pd.DataFrame(data, columns=[el["name"] for el in schema])
        main_dataframe[schema[1]['name']] = pd.to_datetime(main_dataframe[schema[1]['name']], format='%Y-%m-%d %H:%M:%S')

        main_dataframe = main_dataframe.sort_values(by=schema[0]['name'], ascending=False, ignore_index=True)
        if baslangic:
            main_dataframe = main_dataframe[main_dataframe[schema[0]['name']] < int(baslangic.timestamp())*1000].reset_index(drop=True)

        print(f'{_type} datasi yuklendi!')
        return main_dataframe