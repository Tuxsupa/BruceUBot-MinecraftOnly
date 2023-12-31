import asyncio
import contextlib
import time
import datetime
import threading
import json

import discord
import streamlink
import cv2
import numpy as np
import matplotlib.pyplot as plt

from discord.ext import commands
from streamlink.options import Options
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from dotenv import load_dotenv
from utils import default

load_dotenv()
plt.switch_backend('agg')


class Minecraft(commands.Cog):
    def __init__(self, client: default.DiscordBot):
        self.client = client
        self.frame = None
        self.stopMainFlag = False

        self.lock = threading.Lock()
        self.igt = IGT(self.client)
        self.biome = Biome(self.client)
        self.achievement = Achievement(self.client)
        self.coordinates = Coordinates(self.client)
        # self.inventory = Inventory(self.client)
        self.other = Other(self.client)

    def timeToString(self, timeIGT: datetime.time):
        formattedIGT = timeIGT.strftime("%M:%S.%f")
        return formattedIGT[:-3]

    @commands.hybrid_command(aliases=["m"], description="Forsen's Minecraft Status")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.guild_only()
    async def minecraft(self, ctx: commands.Context):
        twitchAPI = self.client.twitchAPI
        if twitchAPI.isIntro is False and twitchAPI.isOnline is True and twitchAPI.game == "Minecraft":
            embed = discord.Embed(title="Forsen's Minecraft Status", description=None, color=0x000000, timestamp=ctx.message.created_at)
            embed.add_field(name="Ingame Time:", value=self.timeToString(self.igt.timeIGT), inline=True)
            embed.add_field(name="Biome:", value=self.biome.biomeText[self.biome.biomeID], inline=True)
            embed.add_field(name="Phase:", value=self.achievement.numberStructute(), inline=True)
            embed.add_field(name="Seeds:", value=self.other.generatingCounter, inline=True)
            embed.add_field(name="Deaths:", value=self.other.deathCounter, inline=True)
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/988994875234082829/1139301216459964436/3x.gif")
            embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text="Bot made by Tuxsuper", icon_url=self.client.DEV.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["c"], description="Forsen's Minecraft Coords")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.guild_only()
    async def coords(self, ctx: commands.Context):
        twitchAPI = self.client.twitchAPI
        if twitchAPI.isIntro is False and twitchAPI.isOnline is True and twitchAPI.game == "Minecraft":
            if len(self.coordinates.coordsList) >= 2:
                x_values = [coord[0] for coord in self.coordinates.coordsList[:-2]]
                z_values = [coord[2] for coord in self.coordinates.coordsList[:-2]]

                plt.plot(x_values, z_values, color='black')
                
                max_x, min_x = max(x_values), min(x_values)
                max_z, min_z = max(z_values), min(z_values)
                
                diff_x = (max_x-min_x)*0.1
                diff_z = (max_z-min_z)*0.1

                plt.xlim(max_x+diff_x, min_x-diff_x)
                plt.ylim(min_z-diff_z, max_z+diff_z)

                img = plt.imread("./assets/images/minecraft/forsenE.png")
                imagebox = OffsetImage(img, zoom=0.1)
                ab = AnnotationBbox(imagebox, (self.coordinates.coordsList[-2:][0][0], self.coordinates.coordsList[-2:][0][2]), frameon=False)
                plt.gca().add_artist(ab)

                for phaseCoords in self.coordinates.achievementCheck:
                    phase = phaseCoords[0]
                    check = phaseCoords[1]

                    if check != -1:
                        continue
                    if len(phaseCoords) < 3:
                        continue

                    coords = phaseCoords[2]

                    plt.scatter(coords[0], coords[2], s=100, zorder=2)
                    plt.annotate(phase, (coords[0], coords[2]), textcoords="offset points", xytext=(0,15), ha='center', fontsize=12)

            plt.xlabel('X Coordinate')
            plt.ylabel('Z Coordinate')
            plt.title('Forsen Coordinates')

            filename = "./assets/images/coordinates.png"
            plt.savefig(filename)
            image = discord.File(filename)

            await ctx.send(file = image)

            plt.close()

    async def startMain(self):
        self.igt.timeIGT = datetime.time(minute=0, second=0, microsecond=0)
        
        self.biome.biomeID = "unknown"
        
        self.achievement.phase = ["Start"]
        
        self.coordinates.coordsList = []
        self.coordinates.achievementCheck = [["Start", 0]] # Dimension POI
        self.coordinates.all_achievementCheck = self.coordinates.achievementCheck # Seed (all) POI
        
        self.other.resultTemplate = None
        self.other.deathCounter = 0
        self.other.generatingCounter = 0
        self.other.isSpectator = False
        
        self.stopMainFlag = False
        self.main_thread = threading.Thread(target=self.main)
        self.main_thread.start()

    async def stopMain(self):
        self.stopMainFlag = True
        self.main_thread.join()

    async def startStreamlink(self):
        session = streamlink.Streamlink()
        _, pluginclass, resolved_url = session.resolve_url("twitch.tv/forsen")

        options = Options()
        options.set("low-latency", True)
        options.set("disable-ads", True)

        with contextlib.suppress(AttributeError):
            options.set("api-header", {"Authorization": self.client.twitchAPI.TWITCH.get_user_auth_token()})
            
        plugin = pluginclass(session, resolved_url, options)
        streams = plugin.streams()
        for stream_interation in streams:
            if stream_interation.startswith("1080p"):
                stream = streams[stream_interation]

        if not streams or not stream:
            print("Stream not found")
            return

        self.cap = cv2.VideoCapture(stream.url)

    def main(self):
        asyncio.run(self.startStreamlink())

        # self.cap = cv2.VideoCapture("./assets/forsen.mp4")
        # self.cap.set(cv2.CAP_PROP_POS_MSEC, (141 * 60 + 00) * 1000)

        igt_thread = threading.Thread(target=self.igt.getIGT)
        igt_thread.start()

        biome_thread = threading.Thread(target=self.biome.getBiome)
        biome_thread.start()

        achievement_thread = threading.Thread(target=self.achievement.getAchievement)
        achievement_thread.start()

        coords_thread = threading.Thread(target=self.coordinates.getCoords)
        coords_thread.start()

        # inventory_thread = threading.Thread(target=self.inventory.getInventory)
        # inventory_thread.start()

        other_thread = threading.Thread(target=self.other.getOthers)
        other_thread.start()

        while not self.stopMainFlag:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    continue

                self.frame = frame

                # cv2.imshow("camCapture", frame)
                # cv2.waitKey(1)

                time.sleep(5 / 1000)

            except Exception:
                continue

        self.cap.release()
        igt_thread.join()
        biome_thread.join()
        achievement_thread.join()
        coords_thread.join()
        # inventory_thread.join()
        other_thread.join()


class IGT():
    def __init__(self, client: default.DiscordBot):
        self.client = client

        self.timeIGT = datetime.time(minute=0, second=0, microsecond=0)

        self.templates = []
        for i in range(10):
            templatePath = f'./assets/images/minecraft/{i}.png'
            template = cv2.imread(templatePath)
            self.templates.append(template)


    def getIGT(self):
        templateSize = [21, 27]
        xPositions = [66, 84, 108, 126, 150, 168, 186]

        breakFlag = False
        while not self.client.minecraft.stopMainFlag:
            time.sleep(1/2)

            with self.client.minecraft.lock:
                frame = self.client.minecraft.frame

            if frame is None:
                continue

            # cv2.imshow("camCapture", frame)
            # cv2.waitKey(1)

            frame = frame[81:108, 1683:1890]

            numbers = []
            for i in range(7):
                windowX = xPositions[i]
                windowY = 0

                window = frame[windowY:windowY + templateSize[1], windowX:windowX + templateSize[0]]

                bestMatchVal = 0
                bestMatchIndex = None

                for j, template in enumerate(self.templates):
                    result = cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED)
                    _, maxVal, _, _ = cv2.minMaxLoc(result)

                    if maxVal >= 0.5 and maxVal > bestMatchVal:
                        bestMatchVal = maxVal
                        bestMatchIndex = j

                if bestMatchIndex is None:
                    breakFlag = True
                    break

                numbers.append(bestMatchIndex)

            if breakFlag:
                breakFlag = False
                continue

            minute = numbers[0] * 10 + numbers[1]
            second = numbers[2] * 10 + numbers[3]
            millisecond = numbers[4] * 100 + numbers[5] * 10 + numbers[6]
            self.timeIGT = datetime.time(minute=minute, second=second, microsecond=millisecond * 1000)


class Biome():
    def __init__(self, client: default.DiscordBot):
        self.client = client

        self.biomeID = "unknown"

        self.biomeTemplate = cv2.imread("./assets/images/minecraft/Biome.png")

        with open("./assets/dictionaries/minecraft/biomes.json", "r", encoding="utf-8") as biomeJson:
            biomeStr = biomeJson.read()
            biomeData = json.loads(biomeStr)
            biomeData["biome_text"][None] = None

            self.biomeIDs = biomeData["biome_ids"]
            self.biomeText = biomeData["biome_text"]

        self.biomeImages = []
        for biomeID in self.biomeIDs:
            image = cv2.imread(f"./assets/images/minecraft/Biomes/{biomeID}.png")
            self.biomeImages.append(image)


    def check_biome_visible(self, frame):
        biomeText = frame[488:516, 0:83]

        result = cv2.matchTemplate(biomeText, self.biomeTemplate, cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, _ = cv2.minMaxLoc(result)

        return maxVal >= 0.5

    def getBiome(self):
        while not self.client.minecraft.stopMainFlag:
            time.sleep(1/5)

            with self.client.minecraft.lock:
                frame = self.client.minecraft.frame

            if frame is None:
                continue

            if self.check_biome_visible(frame):
                # cv2.imshow("camCapture", frame)
                # cv2.waitKey(1)

                yStart = 489
                xStart = 249

                bestMatchVal = 0
                bestMatchIndex = None

                for j, template in enumerate(self.biomeImages):
                    biomeID = frame[yStart:yStart+template.shape[0], xStart:xStart+template.shape[1]]

                    result = cv2.matchTemplate(biomeID, template, cv2.TM_CCOEFF_NORMED)
                    _, maxVal, _, maxLoc = cv2.minMaxLoc(result)

                    if maxVal >= 0.5 and maxLoc[0] == 0 and maxVal > bestMatchVal:
                        bestMatchVal = maxVal
                        bestMatchIndex = j

                if bestMatchIndex is None:
                    continue

                self.biomeID = self.biomeIDs[bestMatchIndex]


class Achievement():
    def __init__(self, client: default.DiscordBot):
        self.client = client

        self.phase = ["Start"]

        with open("./assets/dictionaries/minecraft/achievements.json", "r", encoding="utf-8") as achievementJson:
            achievementStr = achievementJson.read()
            achievementData = json.loads(achievementStr)

            self.achievementPhases = achievementData["achievementPhases"]
            self.achievementPriority = achievementData["achievementPriority"]

        self.templates = []
        for phase in self.achievementPhases:
            templatePath = f'./assets/images/minecraft/{phase}.png'
            template = cv2.imread(templatePath)
            self.templates.append(template)

    def check_priority_phase(self, achievementMatches):
        oldPhase = self.phase[-1]
        highestPrio = self.achievementPriority[oldPhase]

        for match in achievementMatches:
            prio = self.achievementPriority[match]
            if self.client.minecraft.other.isSpectator is False and prio >= highestPrio and match not in self.phase:
                self.phase.append(match)
                highestPrio = prio
                self.client.minecraft.coordinates.achievementCheck.append([match, 0])
                self.client.minecraft.coordinates.all_achievementCheck.append([match, 0])
                self.client.loop.create_task(self.pingStronghold(match, oldPhase))

    async def pingStronghold(self, phase, oldPhase):
        if not self.client.isTest and (phase != oldPhase and phase == "Stronghold"):
            SNIPA_CHANNEL = 1081602472516276294
            PING_ROLE = 1137857293363449866
            discordChannel = await (self.client.get_channel(SNIPA_CHANNEL) or await self.client.fetch_channel(SNIPA_CHANNEL))
            await discordChannel.send(content=f"<@&{PING_ROLE}> THE RUN")

    def numberStructute(self):
        if self.phase[-1] in ("Bastion", "Fortress"):
            if self.phase[-2] in ("Bastion", "Fortress"):
                return f"2nd {self.phase[-1]}"

            return f"1st {self.phase[-1]}"

        return self.phase[-1]

    def getAchievement(self):
        while not self.client.minecraft.stopMainFlag:
            time.sleep(1/5)

            with self.client.minecraft.lock:
                frame = self.client.minecraft.frame

            if frame is None:
                continue

            # cv2.imshow("camCapture", frame)
            # cv2.waitKey(1)

            achievement = frame[882:960, 461:927]

            achievementMatches = []
            for j, template in enumerate(self.templates):
                result = cv2.matchTemplate(achievement, template, cv2.TM_CCOEFF_NORMED)
                _, maxVal, _, _ = cv2.minMaxLoc(result)

                if maxVal >= 0.5:
                    achievementMatches.append(self.achievementPhases[j])

            if not achievementMatches:
                continue

            self.check_priority_phase(achievementMatches)


class Coordinates():
    def __init__(self, client: default.DiscordBot):
        self.client = client
        self.coordsList = []
        self.achievementCheck = [["Start", 0]] # [[phase, number_check_trueCoord]
        self.all_achievementCheck = self.achievementCheck

        self.blockTemplate = cv2.imread("./assets/images/minecraft/Coordinates/Block.png")

        self.templates = []
        for i in range(10):
            templatePath = f'./assets/images/minecraft/Coordinates/{i}.png'
            template = cv2.imread(templatePath)
            self.templates.append(template)

        self.templates.append(cv2.imread("./assets/images/minecraft/Coordinates/minus.png"))

    def check_block_visible(self, frame):
        blockText = frame[303:324, 6:81]

        result = cv2.matchTemplate(blockText, self.blockTemplate, cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, _ = cv2.minMaxLoc(result)

        return maxVal >= 0.5
    
    def get_coord_numbers(self, coords):
        numbers = []
        for i, template in enumerate(self.templates):
            result = cv2.matchTemplate(coords, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.8
            locations = np.where(result >= threshold)

            for [x, y] in zip(*locations[::-1]):
                maxVal = result[(x, y)[::-1]]

                if x % 18 != 0 and (x+30) % 18 != 0 and (x+60) % 18 != 0:
                    continue

                toRemove = []
                isSame = False
                for tup in numbers:
                    if x == tup[0]:
                        isSame = True
                        if maxVal > tup[2]:
                            toRemove.append(tup)


                numbers = [tup for tup in numbers if tup not in toRemove]

                if not toRemove and isSame:
                    continue

                if i == 10:
                    numbers.append((x, "-", maxVal))
                else:
                    numbers.append((x, i, maxVal))
                    
        return numbers
    
    def append_coord_numbers(self, numbers):
        sortedNumbers = sorted(numbers, key=lambda x: x[0])

        coordString = ""
        jump = 0
        coords = []
        for i, [x, number, _] in enumerate(sortedNumbers):
            if (x-jump) % 18 != 0:
                try:
                    coords.append(int(coordString))
                except ValueError:
                    break
                coordString = ""
                jump += 30
                if len(coords) >= 3:
                    break

            coordString += str(number)
        try:
            coords.append(int(coordString))
            self.coordsList.append(coords)
            numbers = np.array(self.coordsList)
            return numbers
        except Exception as e:
            print(e)
            return None

    def remove_outlier_coords(self, numbers):
        diffs = np.diff(numbers, axis=0)
        threshold = 10
        distances = np.linalg.norm(diffs, axis=1)
    
        outlierIndices = [
            i - 1
            for i, distance in enumerate(distances[-2:])
            if distances[-2:][i-1] > threshold and distance > threshold
        ]

        for row in outlierIndices:
            self.coordsList.pop(len(self.coordsList)-2+row)
            if self.achievementCheck[-1][1] >= 0:
                self.achievementCheck[-1][1] -= 1

        if len(self.coordsList) >= 2 and (len(self.achievementCheck) > 0 and len(self.achievementCheck[-1]) < 3):
            if self.achievementCheck[-1][1] == 1:
                self.achievementCheck[-1].append(self.coordsList[-2:][0])
                self.achievementCheck[-1][1] = -1
        
            elif self.achievementCheck[-1][1] == 0:
                self.achievementCheck[-1][1] += 1

    def getCoords(self):
        while not self.client.minecraft.stopMainFlag:
            time.sleep(1/5)

            with self.client.minecraft.lock:
                frame = self.client.minecraft.frame

            if frame is None:
                continue

            if self.check_block_visible(frame):
                coords = frame[302:325, 101:385]

                lowerBound = np.array([170, 170, 170], dtype=np.uint8)
                upperBound = np.array([255, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(coords, lowerBound, upperBound)
                coords = cv2.bitwise_and(coords, coords, mask=mask)

                numbers = self.get_coord_numbers(coords)
                if not numbers:
                    continue

                numbers = self.append_coord_numbers(numbers)
                    
                try:
                    self.remove_outlier_coords(numbers)
                except Exception as e:
                    print(e)


# class Inventory():
#     def __init__(self, client: default.DiscordBot):
#         self.client = client

#         self.craftingTemplate = cv2.imread('./assets/images/minecraft/CraftingNew.png')

#         with open("./assets/dictionaries/minecraft/inventory.json", "r", encoding="utf-8") as inventoryJson:
#             inventoryStr = inventoryJson.read()
#             inventoryData = json.loads(inventoryStr)

#             self.inventoryItems = inventoryData["inventoryItems"]

#         self.itemTemplates = []
#         for item in self.inventoryItems:
#             templatePath = f'./assets/images/minecraft/InventoryIcons/{item}.png'
#             template = cv2.imread(templatePath)
#             self.itemTemplates.append(template)

#     def check_inventory_visible(self, frame):
#         crafting = frame[309:333, 987:1107]

#         # cv2.imshow("camCapture", crafting)
#         # cv2.waitKey(1)

#         result = cv2.matchTemplate(crafting, self.craftingTemplate, cv2.TM_CCOEFF_NORMED)
#         _, maxVal, _, _ = cv2.minMaxLoc(result)

#         return maxVal >= 0.5

#     def getInventory(self):
#         while not self.client.minecraft.stopMainFlag:
#             time.sleep(1/20)

#             with self.client.minecraft.lock:
#                 frame = self.client.minecraft.frame

#             if frame is None:
#                 continue

#             # cv2.imshow("camCapture", frame)
#             # cv2.waitKey(1)

#             isVisible = self.check_inventory_visible(frame)

#             if isVisible:
#                 print("Visible")

#                 xStart = 3
#                 yStart = 3

#                 inventory = frame[540:768, 717:1203]

#                 for i in range(9*4):
#                     item = inventory[yStart:yStart+27, xStart:xStart+48]

#                     for itemTemplate in self.itemTemplates:
#                         result = cv2.matchTemplate(item, itemTemplate, cv2.TM_CCOEFF_NORMED)
#                         _, maxVal, _, _ = cv2.minMaxLoc(result)

#                         if maxVal >= 0.95:
#                             cv2.imshow("camCapture", item)
#                             cv2.waitKey(0)

#                             cv2.imshow("camCapture", itemTemplate)
#                             cv2.waitKey(0)

#                     xStart += 48 + 6

#                     if (i+1) % 9 == 0:
#                         yStart += 48 + 6
#                         xStart = 3

#                         if (i+1) == 27:
#                             yStart += 12


class Other():
    def __init__(self, client: default.DiscordBot):
        self.client = client
        
        self.resultTemplate = None
        self.deathCounter = 0
        self.generatingCounter = 0
        self.isSpectator = False

        self.otherTemplates = (("Loading", (390, 414, 771, 1056), 0.5), ("Generating", (438, 459, 942, 975), 0.85),
                               ("Died", (504, 528, 855, 1062), 0.3), ("Spectator", (555, 576, 879, 1038), 0.4))
        self.templates = []
        for templateText, _, _ in self.otherTemplates:
            templatePath = f'./assets/images/minecraft/{templateText}.png'
            template = cv2.imread(templatePath)
            self.templates.append(template)

    def loading(self, minecraft: Minecraft):
        minecraft.coordinates.coordsList = []
        minecraft.coordinates.achievementCheck = []
        if all(phase in minecraft.achievement.phase for phase in ["Bastion", "Fortress"]):
            if "Nether Exit" not in minecraft.achievement.phase:
                minecraft.achievement.phase.append("Nether Exit")
                minecraft.coordinates.achievementCheck = [["Nether Exit", 0]]
                minecraft.coordinates.all_achievementCheck.append(["Nether Exit", 0])
            elif "Nether Exit" in minecraft.coordinates.all_achievementCheck[-1]:
                minecraft.coordinates.achievementCheck = [minecraft.coordinates.all_achievementCheck[-2]]

    def generating(self, minecraft: Minecraft):
        self.generatingCounter += 1
        minecraft.igt.timeIGT = datetime.time(minute=0, second=0, microsecond=0)
        minecraft.biome.biomeID = "unknown"
        minecraft.achievement.phase = ["Start"]
        minecraft.coordinates.coordsList = []
        minecraft.coordinates.achievementCheck = [["Start", 0]]
        minecraft.coordinates.all_achievementCheck = [["Start", 0]]
        self.isSpectator = False

    def death(self):
        self.deathCounter += 1

    def spectator(self):
        self.isSpectator = True

    def getOthers(self):
        minecraft = self.client.minecraft
        while not minecraft.stopMainFlag:
            time.sleep(1/30)

            with minecraft.lock:
                frame = minecraft.frame

            if frame is None:
                continue

            # cv2.imshow("camCapture", frame)
            # cv2.waitKey(1)

            newResultTemplate = None
            for j, template in enumerate(self.templates):
                otherTemplate = self.otherTemplates[j][1]
                otherTemplate = frame[otherTemplate[0]:otherTemplate[1], otherTemplate[2]:otherTemplate[3]]

                result = cv2.matchTemplate(otherTemplate, template, cv2.TM_CCOEFF_NORMED)
                _, maxVal, _, _ = cv2.minMaxLoc(result)

                if maxVal >= self.otherTemplates[j][2]:
                    newResultTemplate = self.otherTemplates[j][0]
                    break

            if newResultTemplate != self.resultTemplate:
                self.resultTemplate = newResultTemplate

                if self.resultTemplate is None:
                    continue

                match newResultTemplate:
                    case "Loading":
                        self.loading(minecraft)
                    case "Generating":
                        self.generating(minecraft)
                    case "Died":
                        self.death()
                    case "Spectator":
                        self.spectator()


async def setup(client: default.DiscordBot):
    await client.add_cog(Minecraft(client))
