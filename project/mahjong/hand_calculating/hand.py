# -*- coding: utf-8 -*-
import math

import copy
from functools import reduce

from mahjong.ai.agari import Agari
from mahjong import yaku
from mahjong.hand_calculating.divider import HandDivider
from mahjong.hand_calculating.fu import HandFuCalculator
from mahjong.hand_calculating.scores import ScoresCalculator
from mahjong.meld import Meld
from mahjong.tile import TilesConverter
from mahjong.constants import EAST, SOUTH, WEST, NORTH, CHUN, HATSU, HAKU, TERMINAL_INDICES, HONOR_INDICES
from mahjong.utils import is_chi, is_pon, is_pair, is_sou, is_pin, is_man, plus_dora, simplify
from utils.settings_handler import settings


class FinishedHand(object):

    def estimate_hand_value(self,
                            tiles,
                            win_tile,
                            is_tsumo=False,
                            is_riichi=False,
                            is_dealer=False,
                            is_ippatsu=False,
                            is_rinshan=False,
                            is_chankan=False,
                            is_haitei=False,
                            is_houtei=False,
                            is_daburu_riichi=False,
                            is_nagashi_mangan=False,
                            is_tenhou=False,
                            is_renhou=False,
                            is_chiihou=False,
                            melds=None,
                            dora_indicators=None,
                            player_wind=None,
                            round_wind=None):
        """
        :param tiles: array with 14 tiles in 136-tile format
        :param win_tile: tile that caused win (ron or tsumo)
        :param is_tsumo:
        :param is_riichi:
        :param is_dealer:
        :param is_ippatsu:
        :param is_rinshan:
        :param is_chankan:
        :param is_haitei:
        :param is_houtei:
        :param is_tenhou:
        :param is_renhou:
        :param is_chiihou:
        :param is_daburu_riichi:
        :param is_nagashi_mangan:
        :param melds: array with Meld objects
        :param dora_indicators: array of tiles in 136-tile format
        :param player_wind: index of player wind
        :param round_wind: index of round wind
        :return: The dictionary with hand cost or error response

        {"cost": {'main': 1000, 'additional': 0}, "han": 1, "fu": 30, "error": None, "hand_yaku": []}
        {"cost": None, "han": 0, "fu": 0, "error": "Hand is not valid", "hand_yaku": []}
        """

        if not melds:
            melds = []

        opened_melds = [x for x in melds if x.opened]
        is_open_hand = len(opened_melds) > 0

        # TODO Deprecated. Change it to melds in all places
        called_kan_indices = []
        kan_indices_136 = []
        for meld in melds:
            if meld.type == Meld.KAN or meld.type == Meld.CHANKAN:
                called_kan_indices.append(meld.tiles[0] // 4)
                kan_indices_136 = [meld.tiles[0]]

        open_sets_34 = []
        for meld in opened_melds:
            open_sets_34.append([x // 4 for x in meld.tiles[:3]])

        if not dora_indicators:
            dora_indicators = []

        agari = Agari()
        cost = None
        error = None
        hand_yaku = []
        han = 0
        fu = 0
        scores_calculator = ScoresCalculator()

        def return_response():
            return {'cost': cost, 'error': error, 'han': han, 'fu': fu, 'hand_yaku': hand_yaku}

        # special situation
        if is_nagashi_mangan:
            hand_yaku.append(yaku.nagashi_mangan)
            fu = 30
            han = yaku.nagashi_mangan.han['closed']
            cost = scores_calculator.calculate_scores(han, fu, is_tsumo, is_dealer)
            return return_response()

        if win_tile not in tiles:
            error = "Win tile not in the hand"
            return return_response()

        if is_riichi and is_open_hand:
            error = "Riichi can't be declared with open hand"
            return return_response()

        if is_ippatsu and is_open_hand:
            error = "Ippatsu can't be declared with open hand"
            return return_response()

        if is_ippatsu and not is_riichi and not is_daburu_riichi:
            error = "Ippatsu can't be declared without riichi"
            return return_response()

        tiles_34 = TilesConverter.to_34_array(tiles)
        divider = HandDivider()
        fu_calculator = HandFuCalculator()

        if not agari.is_agari(tiles_34, open_sets_34):
            error = 'Hand is not winning'
            return return_response()

        hand_options = divider.divide_hand(tiles_34, open_sets_34, called_kan_indices)

        calculated_hands = []
        for hand in hand_options:
            cost = None
            error = None
            hand_yaku = []
            han = 0
            fu = 0

            if is_tsumo or is_open_hand:
                fu += 20
            else:
                fu += 30

            pon_sets = [x for x in hand if is_pon(x)]
            chi_sets = [x for x in hand if is_chi(x)]
            additional_fu = fu_calculator.calculate_additional_fu(win_tile,
                                                                  hand,
                                                                  is_tsumo,
                                                                  player_wind,
                                                                  round_wind,
                                                                  open_sets_34,
                                                                  called_kan_indices)

            if additional_fu == 0 and len(chi_sets) == 4:
                """
                - A hand without pon and kan sets, so it should contains all sequences and a pair
                - The pair should be not valued
                - The waiting must be an open wait (on 2 different tiles)
                - Hand should be closed
                """
                if is_open_hand:
                    fu += 2
                    is_pinfu = False
                else:
                    is_pinfu = True
            else:
                fu += additional_fu
                is_pinfu = False

            if is_tsumo:
                if not is_open_hand:
                    hand_yaku.append(yaku.tsumo)

                # pinfu + tsumo always is 20 fu
                if not is_pinfu:
                    fu += 2

            if is_pinfu:
                hand_yaku.append(yaku.pinfu)

            is_chitoitsu = self.is_chitoitsu(hand)
            # let's skip hand that looks like chitoitsu, but it contains open sets
            if is_chitoitsu and is_open_hand:
                continue

            if is_chitoitsu:
                hand_yaku.append(yaku.chiitoitsu)

            is_tanyao = self.is_tanyao(hand)
            if is_open_hand and not settings.OPEN_TANYAO:
                is_tanyao = False

            if is_tanyao:
                hand_yaku.append(yaku.tanyao)

            if is_riichi and not is_daburu_riichi:
                hand_yaku.append(yaku.riichi)

            if is_daburu_riichi:
                hand_yaku.append(yaku.daburu_riichi)

            if is_ippatsu:
                hand_yaku.append(yaku.ippatsu)

            if is_rinshan:
                hand_yaku.append(yaku.rinshan)

            if is_chankan:
                hand_yaku.append(yaku.chankan)

            if is_haitei:
                hand_yaku.append(yaku.haitei)

            if is_houtei:
                hand_yaku.append(yaku.houtei)

            if is_renhou:
                hand_yaku.append(yaku.renhou)

            if is_tenhou:
                hand_yaku.append(yaku.tenhou)

            if is_chiihou:
                hand_yaku.append(yaku.chiihou)

            if self.is_honitsu(hand):
                hand_yaku.append(yaku.honitsu)

            if self.is_chinitsu(hand):
                hand_yaku.append(yaku.chinitsu)

            if self.is_tsuisou(hand):
                hand_yaku.append(yaku.tsuisou)

            if self.is_honroto(hand):
                hand_yaku.append(yaku.honroto)

            if self.is_chinroto(hand):
                hand_yaku.append(yaku.chinroto)

            # small optimization, try to detect yaku with chi required sets only if we have chi sets in hand
            if len(chi_sets):
                if self.is_chanta(hand):
                    hand_yaku.append(yaku.chanta)

                if self.is_junchan(hand):
                    hand_yaku.append(yaku.junchan)

                if self.is_ittsu(hand):
                    hand_yaku.append(yaku.ittsu)

                if not is_open_hand:
                    if self.is_ryanpeiko(hand):
                        hand_yaku.append(yaku.ryanpeiko)
                    elif self.is_iipeiko(hand):
                        hand_yaku.append(yaku.iipeiko)

                if self.is_sanshoku(hand):
                    hand_yaku.append(yaku.sanshoku)

            # small optimization, try to detect yaku with pon required sets only if we have pon sets in hand
            if len(pon_sets):
                if self.is_toitoi(hand):
                    hand_yaku.append(yaku.toitoi)

                if self.is_sanankou(win_tile, hand, open_sets_34, is_tsumo):
                    hand_yaku.append(yaku.sanankou)

                if self.is_sanshoku_douko(hand):
                    hand_yaku.append(yaku.sanshoku_douko)

                if self.is_shosangen(hand):
                    hand_yaku.append(yaku.shosangen)

                if self.is_haku(hand):
                    hand_yaku.append(yaku.haku)

                if self.is_hatsu(hand):
                    hand_yaku.append(yaku.hatsu)

                if self.is_chun(hand):
                    hand_yaku.append(yaku.hatsu)

                if self.is_east(hand, player_wind, round_wind):
                    if player_wind == EAST:
                        hand_yaku.append(yaku.yakuhai_place)

                    if round_wind == EAST:
                        hand_yaku.append(yaku.yakuhai_round)

                if self.is_south(hand, player_wind, round_wind):
                    if player_wind == SOUTH:
                        hand_yaku.append(yaku.yakuhai_place)

                    if round_wind == SOUTH:
                        hand_yaku.append(yaku.yakuhai_round)

                if self.is_west(hand, player_wind, round_wind):
                    if player_wind == WEST:
                        hand_yaku.append(yaku.yakuhai_place)

                    if round_wind == WEST:
                        hand_yaku.append(yaku.yakuhai_round)

                if self.is_north(hand, player_wind, round_wind):
                    if player_wind == NORTH:
                        hand_yaku.append(yaku.yakuhai_place)

                    if round_wind == NORTH:
                        hand_yaku.append(yaku.yakuhai_round)

                if self.is_daisangen(hand):
                    hand_yaku.append(yaku.daisangen)

                if self.is_shosuushi(hand):
                    hand_yaku.append(yaku.shosuushi)

                if self.is_daisuushi(hand):
                    hand_yaku.append(yaku.daisuushi)

                if self.is_ryuisou(hand):
                    hand_yaku.append(yaku.ryuisou)

                if not is_open_hand and self.is_chuuren_poutou(hand):
                    if tiles_34[win_tile // 4] == 2:
                        hand_yaku.append(yaku.daburu_chuuren_poutou)
                    else:
                        hand_yaku.append(yaku.chuuren_poutou)

                if not is_open_hand and self.is_suuankou(win_tile, hand, is_tsumo):
                    if tiles_34[win_tile // 4] == 2:
                        hand_yaku.append(yaku.suuankou_tanki)
                    else:
                        hand_yaku.append(yaku.suuankou)

                if self.is_sankantsu(melds):
                    hand_yaku.append(yaku.sankantsu)

                if self.is_suukantsu(melds):
                    hand_yaku.append(yaku.suukantsu)

            # chitoitsu is always 25 fu
            if is_chitoitsu:
                fu = 25

            # yakuman is not connected with other yaku
            yakuman_list = [x for x in hand_yaku if x.is_yakuman]
            if yakuman_list:
                hand_yaku = yakuman_list

            # calculate han
            for item in hand_yaku:
                if is_open_hand and item.han['open']:
                    han += item.han['open']
                else:
                    han += item.han['closed']

            # round up
            # 22 -> 30 and etc.
            if fu != 25:
                fu = int(math.ceil(fu / 10.0)) * 10

            if han == 0 or (han == 1 and fu < 30):
                error = 'Not valid han ({0}) and fu ({1})'.format(han, fu)
                cost = None
            # else:

            # we can add dora han only if we have other yaku in hand
            # and if we don't have yakuman
            if not yakuman_list:
                tiles_for_dora = tiles + kan_indices_136
                count_of_dora = 0
                count_of_aka_dora = 0
                for tile in tiles_for_dora:
                    count_of_dora += plus_dora(tile, dora_indicators)

                if count_of_dora:
                    yaku_item = yaku.dora
                    yaku_item.han['open'] = count_of_dora
                    yaku_item.han['closed'] = count_of_dora
                    hand_yaku.append(yaku_item)
                    han += count_of_dora

                if count_of_aka_dora:
                    yaku_item = yaku.aka_dora
                    yaku_item.han['open'] = count_of_aka_dora
                    yaku_item.han['closed'] = count_of_aka_dora
                    hand_yaku.append(yaku_item)
                    han += count_of_aka_dora

            if not error:
                cost = scores_calculator.calculate_scores(han, fu, is_tsumo, is_dealer)

            calculated_hand = {
                'cost': cost,
                'error': error,
                'hand_yaku': hand_yaku,
                'han': han,
                'fu': fu
            }
            calculated_hands.append(calculated_hand)

        # exception hand
        if not is_open_hand and self.is_kokushi(tiles_34):
            if tiles_34[win_tile // 4] == 2:
                han = yaku.daburu_kokushi.han['closed']
            else:
                han = yaku.kokushi.han['closed']
            fu = 0
            cost = scores_calculator.calculate_scores(han, fu, is_tsumo, is_dealer)
            calculated_hands.append({
                'cost': cost,
                'error': None,
                'hand_yaku': [yaku.kokushi],
                'han': han,
                'fu': fu
            })

        # let's use cost for most expensive hand
        calculated_hands = sorted(calculated_hands, key=lambda x: (x['han'], x['fu']), reverse=True)

        calculated_hand = calculated_hands[0]
        cost = calculated_hand['cost']
        error = calculated_hand['error']
        hand_yaku = calculated_hand['hand_yaku']
        han = calculated_hand['han']
        fu = calculated_hand['fu']

        return return_response()

    def is_chitoitsu(self, hand):
        """
        Hand contains only pairs
        :param hand: list of hand's sets
        :return: boolean
        """
        return len(hand) == 7

    def is_tanyao(self, hand):
        """
        Hand without 1, 9, dragons and winds
        :param hand: list of hand's sets
        :return: boolean
        """
        indices = reduce(lambda z, y: z + y, hand)
        result = TERMINAL_INDICES + HONOR_INDICES
        return not any(x in result for x in indices)

    def is_iipeiko(self, hand):
        """
        Hand with two identical chi
        :param hand: list of hand's sets
        :return: boolean
        """
        chi_sets = [i for i in hand if is_chi(i)]

        count_of_identical_chi = 0
        for x in chi_sets:
            count = 0
            for y in chi_sets:
                if x == y:
                    count += 1
            if count > count_of_identical_chi:
                count_of_identical_chi = count

        return count_of_identical_chi >= 2

    def is_ryanpeiko(self, hand):
        """
        The hand contains two different Iipeikou’s
        :param hand: list of hand's sets
        :return: boolean
        """
        chi_sets = [i for i in hand if is_chi(i)]
        count_of_identical_chi = []
        for x in chi_sets:
            count = 0
            for y in chi_sets:
                if x == y:
                    count += 1
            count_of_identical_chi.append(count)

        return len([x for x in count_of_identical_chi if x >= 2]) == 4

    def is_toitoi(self, hand):
        """
        The hand consists of all pon sets (and of course a pair), no sequences.
        :param hand: list of hand's sets
        :return: boolean
        """
        count_of_pon = len([i for i in hand if is_pon(i)])
        return count_of_pon == 4

    def is_sankantsu(self, melds):
        """
        The hand with three kan sets
        :param hand: list of hand's sets
        :param melds: array of Meld objects
        :return: boolean
        """
        kan_sets = [x for x in melds if x.type == Meld.KAN]
        return len(kan_sets) == 3

    def is_honroto(self, hand):
        """
        All tiles are terminals or honours
        :param hand: list of hand's sets
        :return: boolean
        """
        indices = reduce(lambda z, y: z + y, hand)
        result = HONOR_INDICES + TERMINAL_INDICES
        return all(x in result for x in indices)

    def is_sanankou(self, win_tile, hand, open_sets, is_tsumo):
        """
        Three closed pon sets, the other sets need not to be closed
        :param win_tile: 136 tiles format
        :param hand: list of hand's sets
        :param open_sets: list of open sets
        :param is_tsumo:
        :return: true|false
        """
        win_tile //= 4

        chi_sets = [x for x in hand if (is_chi(x) and win_tile in x and x not in open_sets)]
        pon_sets = [x for x in hand if is_pon(x)]

        closed_pon_sets = []
        for item in pon_sets:
            if item in open_sets:
                continue

            # if we do the ron on syanpon wait our pon will be consider as open
            # and it is not 789999 set
            if win_tile in item and not is_tsumo and not len(chi_sets):
                continue

            closed_pon_sets.append(item)

        return len(closed_pon_sets) == 3

    def is_shosangen(self, hand):
        """
        Hand with two dragon pon sets and one dragon pair
        :param hand: list of hand's sets
        :return: boolean
        """
        dragons = [CHUN, HAKU, HATSU]
        count_of_conditions = 0
        for item in hand:
            # dragon pon or pair
            if (is_pair(item) or is_pon(item)) and item[0] in dragons:
                count_of_conditions += 1

        return count_of_conditions == 3

    def is_chanta(self, hand):
        """
        Every set must have at least one terminal or honour tile, and the pair must be of
        a terminal or honour tile. Must contain at least one sequence (123 or 789).
        :param hand: list of hand's sets
        :return: boolean
        """

        def tile_in_indices(item_set, indices_array):
            for x in item_set:
                if x in indices_array:
                    return True
            return False

        honor_sets = 0
        terminal_sets = 0
        count_of_chi = 0
        for item in hand:
            if is_chi(item):
                count_of_chi += 1

            if tile_in_indices(item, TERMINAL_INDICES):
                terminal_sets += 1

            if tile_in_indices(item, HONOR_INDICES):
                honor_sets += 1

        if count_of_chi == 0:
            return False

        return terminal_sets + honor_sets == 5 and terminal_sets != 0 and honor_sets != 0

    def is_junchan(self, hand):
        """
        Every set must have at least one terminal, and the pair must be of
        a terminal tile. Must contain at least one sequence (123 or 789).
        :param hand: list of hand's sets
        :return: boolean
        """

        def tile_in_indices(item_set, indices_array):
            for x in item_set:
                if x in indices_array:
                    return True
            return False

        terminal_sets = 0
        count_of_chi = 0
        for item in hand:
            if is_chi(item):
                count_of_chi += 1

            if tile_in_indices(item, TERMINAL_INDICES):
                terminal_sets += 1

        if count_of_chi == 0:
            return False

        return terminal_sets == 5

    def is_ittsu(self, hand):
        """
        Three sets of same suit: 1-2-3, 4-5-6, 7-8-9
        :param hand: list of hand's sets
        :return: boolean
        """

        chi_sets = [i for i in hand if is_chi(i)]
        if len(chi_sets) < 3:
            return False

        sou_chi = []
        pin_chi = []
        man_chi = []
        for item in chi_sets:
            if is_sou(item[0]):
                sou_chi.append(item)
            elif is_pin(item[0]):
                pin_chi.append(item)
            elif is_man(item[0]):
                man_chi.append(item)

        sets = [sou_chi, pin_chi, man_chi]

        for suit_item in sets:
            if len(suit_item) < 3:
                continue

            casted_sets = []

            for set_item in suit_item:
                # cast tiles indices to 0..8 representation
                casted_sets.append([simplify(set_item[0]),
                                    simplify(set_item[1]),
                                    simplify(set_item[2])])

            if [0, 1, 2] in casted_sets and [3, 4, 5] in casted_sets and [6, 7, 8] in casted_sets:
                return True

        return False

    def is_sanshoku(self, hand):
        """
        The same chi in three suits
        :param hand: list of hand's sets
        :return: boolean
        """
        chi_sets = [i for i in hand if is_chi(i)]
        if len(chi_sets) < 3:
            return False

        sou_chi = []
        pin_chi = []
        man_chi = []
        for item in chi_sets:
            if is_sou(item[0]):
                sou_chi.append(item)
            elif is_pin(item[0]):
                pin_chi.append(item)
            elif is_man(item[0]):
                man_chi.append(item)

        for sou_item in sou_chi:
            for pin_item in pin_chi:
                for man_item in man_chi:
                    # cast tile indices to 0..8 representation
                    sou_item = [simplify(x) for x in sou_item]
                    pin_item = [simplify(x) for x in pin_item]
                    man_item = [simplify(x) for x in man_item]
                    if sou_item == pin_item == man_item:
                        return True
        return False

    def is_sanshoku_douko(self, hand):
        """
        Three pon sets consisting of the same numbers in all three suits
        :param hand: list of hand's sets
        :return: boolean
        """
        pon_sets = [i for i in hand if is_pon(i)]
        if len(pon_sets) < 3:
            return False

        sou_pon = []
        pin_pon = []
        man_pon = []
        for item in pon_sets:
            if is_sou(item[0]):
                sou_pon.append(item)
            elif is_pin(item[0]):
                pin_pon.append(item)
            elif is_man(item[0]):
                man_pon.append(item)

        for sou_item in sou_pon:
            for pin_item in pin_pon:
                for man_item in man_pon:
                    # cast tile indices to 1..9 representation
                    sou_item = [simplify(x) for x in sou_item]
                    pin_item = [simplify(x) for x in pin_item]
                    man_item = [simplify(x) for x in man_item]
                    if sou_item == pin_item == man_item:
                        return True
        return False

    def is_honitsu(self, hand):
        """
        The hand contains tiles from a single suit plus honours.
        :param hand: list of hand's sets
        :return: boolean
        """
        honor_sets = 0
        sou_sets = 0
        pin_sets = 0
        man_sets = 0
        for item in hand:
            if item[0] in HONOR_INDICES:
                honor_sets += 1

            if is_sou(item[0]):
                sou_sets += 1
            elif is_pin(item[0]):
                pin_sets += 1
            elif is_man(item[0]):
                man_sets += 1

        sets = [sou_sets, pin_sets, man_sets]
        only_one_suit = len([x for x in sets if x != 0]) == 1

        return only_one_suit and honor_sets != 0

    def is_chinitsu(self, hand):
        """
        The hand contains tiles from a single suit
        :param hand: list of hand's sets
        :return: boolean
        """
        honor_sets = 0
        sou_sets = 0
        pin_sets = 0
        man_sets = 0
        for item in hand:
            if item[0] in HONOR_INDICES:
                honor_sets += 1

            if is_sou(item[0]):
                sou_sets += 1
            elif is_pin(item[0]):
                pin_sets += 1
            elif is_man(item[0]):
                man_sets += 1

        sets = [sou_sets, pin_sets, man_sets]
        only_one_suit = len([x for x in sets if x != 0]) == 1

        return only_one_suit and honor_sets == 0

    def is_haku(self, hand):
        """
        Pon of white dragons
        :param hand: list of hand's sets
        :return: boolean
        """
        return len([x for x in hand if is_pon(x) and x[0] == HAKU]) == 1

    def is_hatsu(self, hand):
        """
        Pon of green dragons
        :param hand: list of hand's sets
        :return: boolean
        """
        return len([x for x in hand if is_pon(x) and x[0] == HATSU]) == 1

    def is_chun(self, hand):
        """
        Pon of red dragons
        :param hand: list of hand's sets
        :return: boolean
        """
        return len([x for x in hand if is_pon(x) and x[0] == CHUN]) == 1

    def is_east(self, hand, player_wind, round_wind):
        """
        Pon of east winds
        :param hand: list of hand's sets
        :param player_wind: index of player wind
        :param round_wind: index of round wind
        :return: boolean
        """

        if len([x for x in hand if is_pon(x) and x[0] == player_wind]) == 1 and player_wind == EAST:
            return True

        if len([x for x in hand if is_pon(x) and x[0] == round_wind]) == 1 and round_wind == EAST:
            return True

        return False

    def is_south(self, hand, player_wind, round_wind):
        """
        Pon of south winds
        :param hand: list of hand's sets
        :param player_wind: index of player wind
        :param round_wind: index of round wind
        :return: boolean
        """

        if len([x for x in hand if is_pon(x) and x[0] == player_wind]) == 1 and player_wind == SOUTH:
            return True

        if len([x for x in hand if is_pon(x) and x[0] == round_wind]) == 1 and round_wind == SOUTH:
            return True

        return False

    def is_west(self, hand, player_wind, round_wind):
        """
        Pon of west winds
        :param hand: list of hand's sets
        :param player_wind: index of player wind
        :param round_wind: index of round wind
        :return: boolean
        """

        if len([x for x in hand if is_pon(x) and x[0] == player_wind]) == 1 and player_wind == WEST:
            return True

        if len([x for x in hand if is_pon(x) and x[0] == round_wind]) == 1 and round_wind == WEST:
            return True

        return False

    def is_north(self, hand, player_wind, round_wind):
        """
        Pon of north winds
        :param hand: list of hand's sets
        :param player_wind: index of player wind
        :param round_wind: index of round wind
        :return: boolean
        """

        if len([x for x in hand if is_pon(x) and x[0] == player_wind]) == 1 and player_wind == NORTH:
            return True

        if len([x for x in hand if is_pon(x) and x[0] == round_wind]) == 1 and round_wind == NORTH:
            return True

        return False

    def is_daisangen(self, hand):
        """
        The hand contains three sets of dragons
        :param hand: list of hand's sets
        :return: boolean
        """
        count_of_dragon_pon_sets = 0
        for item in hand:
            if is_pon(item) and item[0] in [CHUN, HAKU, HATSU]:
                count_of_dragon_pon_sets += 1
        return count_of_dragon_pon_sets == 3

    def is_shosuushi(self, hand):
        """
        The hand contains three sets of winds and a pair of the remaining wind.
        :param hand: list of hand's sets
        :return: boolean
        """
        pon_sets = [x for x in hand if is_pon(x)]
        if len(pon_sets) < 3:
            return False

        count_of_wind_sets = 0
        wind_pair = 0
        winds = [EAST, SOUTH, WEST, NORTH]
        for item in hand:
            if is_pon(item) and item[0] in winds:
                count_of_wind_sets += 1

            if is_pair(item) and item[0] in winds:
                wind_pair += 1

        return count_of_wind_sets == 3 and wind_pair == 1

    def is_daisuushi(self, hand):
        """
        The hand contains four sets of winds
        :param hand: list of hand's sets
        :return: boolean
        """
        pon_sets = [x for x in hand if is_pon(x)]
        if len(pon_sets) != 4:
            return False

        count_wind_sets = 0
        winds = [EAST, SOUTH, WEST, NORTH]
        for item in pon_sets:
            if is_pon(item) and item[0] in winds:
                count_wind_sets += 1

        return count_wind_sets == 4

    def is_tsuisou(self, hand):
        """
        Hand composed entirely of honour tiles.
        :param hand: list of hand's sets
        :return: boolean
        """
        indices = reduce(lambda z, y: z + y, hand)
        return all(x in HONOR_INDICES for x in indices)

    def is_chinroto(self, hand):
        """
        Hand composed entirely of terminal tiles.
        :param hand: list of hand's sets
        :return: boolean
        """
        indices = reduce(lambda z, y: z + y, hand)
        return all(x in TERMINAL_INDICES for x in indices)

    def is_kokushi(self, tiles_34):
        """
        A hand composed of one of each of the terminals and honour tiles plus
        any tile that matches anything else in the hand.
        :param tiles_34:
        :return: boolean
        """
        if (tiles_34[0] * tiles_34[8] * tiles_34[9] * tiles_34[17] * tiles_34[18] *
                tiles_34[26] * tiles_34[27] * tiles_34[28] * tiles_34[29] * tiles_34[30] *
                tiles_34[31] * tiles_34[32] * tiles_34[33] == 2):
            return True

    def is_ryuisou(self, hand):
        """
        Hand composed entirely of green tiles. Green tiles are: green dragons and 2, 3, 4, 6 and 8 of sou.
        :param hand: list of hand's sets
        :return: boolean
        """
        green_indices = [19, 20, 21, 23, 25, HATSU]
        indices = reduce(lambda z, y: z + y, hand)
        return all(x in green_indices for x in indices)

    def is_suuankou(self, win_tile, hand, is_tsumo):
        """
        Four closed pon sets
        :param win_tile: 136 tiles format
        :param hand: list of hand's sets
        :param is_tsumo:
        :return: boolean
        """
        win_tile //= 4
        closed_hand = []
        for item in hand:
            # if we do the ron on syanpon wait our pon will be consider as open
            if is_pon(item) and win_tile in item and not is_tsumo:
                continue

            closed_hand.append(item)

        count_of_pon = len([i for i in closed_hand if is_pon(i)])
        return count_of_pon == 4

    def is_chuuren_poutou(self, hand):
        """
        The hand contains 1-1-1-2-3-4-5-6-7-8-9-9-9 of one suit, plus any other tile of the same suit.
        :param hand: list of hand's sets
        :return: boolean
        """

        sou_sets = 0
        pin_sets = 0
        man_sets = 0
        honor_sets = 0
        for item in hand:
            if is_sou(item[0]):
                sou_sets += 1
            elif is_pin(item[0]):
                pin_sets += 1
            elif is_man(item[0]):
                man_sets += 1
            else:
                honor_sets += 1

        sets = [sou_sets, pin_sets, man_sets]
        only_one_suit = len([x for x in sets if x != 0]) == 1
        if not only_one_suit or honor_sets > 0:
            return False

        indices = reduce(lambda z, y: z + y, hand)
        # cast tile indices to 0..8 representation
        indices = [simplify(x) for x in indices]

        # 1-1-1
        if len([x for x in indices if x == 0]) < 3:
            return False

        # 9-9-9
        if len([x for x in indices if x == 8]) < 3:
            return False

        # 1-2-3-4-5-6-7-8-9 and one tile to any of them
        indices.remove(0)
        indices.remove(0)
        indices.remove(8)
        indices.remove(8)
        for x in range(0, 9):
            if x in indices:
                indices.remove(x)

        if len(indices) == 1:
            return True

        return False

    def is_suukantsu(self, melds):
        """
        The hand with four kan sets
        :param hand: list of hand's sets
        :param melds: array of Meld objects
        :return: boolean
        """
        kan_sets = [x for x in melds if x.type == Meld.KAN]
        return len(kan_sets) == 4

