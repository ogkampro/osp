from flask import Blueprint, request, url_for, render_template, redirect, flash
from flask_security import current_user, login_required
from sqlalchemy.sql.expression import func
import hashlib

from classes.shared import db
from classes import settings
from classes import RecordedVideo
from classes import subscriptions
from classes import views
from classes import Channel
from classes import Stream
from classes import Sec
from classes import banList
from classes import stickers
from classes import panel

from globals.globalvars import defaultChatDomain

from functions import themes
from functions import securityFunc
from functions import cachedDbCalls

liveview_bp = Blueprint("liveview", __name__, url_prefix="/view")


@liveview_bp.route("/<loc>/")
def view_page(loc):
    sysSettings = cachedDbCalls.getSystemSettings()

    # requestedChannel = Channel.Channel.query.filter_by(channelLoc=loc).first()
    requestedChannel = cachedDbCalls.getChannelByLoc(loc)
    if requestedChannel is not None:

        if requestedChannel.private:
            if current_user.is_authenticated:
                if (
                    current_user.id != requestedChannel.owningUser
                    and current_user.has_role("Admin") is False
                ):
                    flash("No Such Stream at URL", "error")
                    return redirect(url_for("root.main_page"))
            else:
                flash("No Such Stream at URL", "error")
                return redirect(url_for("root.main_page"))

        if requestedChannel.protected and sysSettings.protectionEnabled:
            if not securityFunc.check_isValidChannelViewer(requestedChannel.id):
                return render_template(
                    themes.checkOverride("channelProtectionAuth.html")
                )

            # Reload due to detached session during Valid User Check:
            requestedChannel = cachedDbCalls.getChannelByLoc(loc)

        # Pull ejabberd Chat Options for Room
        # from app import ejabberd
        # chatOptions = ejabberd.get_room_options(requestedChannel.channelLoc, 'conference.' + sysSettings.siteAddress)
        # for option in chatOptions:
        #    print(option)

        # Create queries for banned words and banned messages, to be used later where needed.
        bwQuery = banList.chatBannedWords.query.with_entities(banList.chatBannedWords.word)

        channelBmQuery = banList.chatBannedMessages.query.filter_by(
            channelLoc=requestedChannel.channelLoc
        ).with_entities(banList.chatBannedMessages.msgID)

        streamData = Stream.Stream.query.filter_by(
            active=True, streamKey=requestedChannel.streamKey
        )

        chatOnly = request.args.get("chatOnly")

        # Grab List of Stickers for Chat

        stickerList = []
        stickerSelectorList = {"builtin": [], "global": [], "channel": []}

        # Build Built-In Stickers
        builtinStickerList = [
            {"name": "oe-angry", "filename": "angry.png"},
            {"name": "oe-smiling", "filename": "smiling.png"},
            {"name": "oe-surprised", "filename": "surprised.png"},
            {"name": "oe-cry", "filename": "cry.png"},
            {"name": "oe-frown", "filename": "frown.png"},
            {"name": "oe-laugh", "filename": "laugh.png"},
            {"name": "oe-think", "filename": "thinking.png"},
            {"name": "oe-thumbsup", "filename": "thumbsup.png"},
            {"name": "oe-thumbsdown", "filename": "thumbsdown.png"},
            {"name": "oe-heart", "filename": "heart.png"},
            {"name": "oe-star", "filename": "star.png"},
            {"name": "oe-fire", "filename": "fire.png"},
            {"name": "oe-checkmark", "filename": "checkmark.png"},
        ]
        for sticker in builtinStickerList:
            newSticker = {
                "name": sticker["name"],
                "file": "/static/img/stickers/" + sticker["filename"],
                "category": "builtin",
            }
            stickerList.append(newSticker)
            stickerSelectorList["builtin"].append(newSticker)

        # Build Global Stickers
        stickerQuery = stickers.stickers.query.filter_by(channelID=None).all()
        for sticker in stickerQuery:

            category = "global"
            stickerFolder = "/images/stickers/"

            newSticker = {
                "name": sticker.name,
                "file": stickerFolder + sticker.filename,
                "category": category,
            }
            stickerList.append(newSticker)
            stickerSelectorList[category].append(newSticker)

        # Build Channel Stickers
        stickerQuery = stickers.stickers.query.filter_by(
            channelID=requestedChannel.id
        ).all()
        for sticker in stickerQuery:

            category = "channel"
            stickerFolder = "/images/stickers/" + requestedChannel.channelLoc + "/"

            newSticker = {
                "name": sticker.name,
                "file": stickerFolder + sticker.filename,
                "category": category,
            }
            stickerList.append(newSticker)
            stickerSelectorList[category].append(newSticker)

        if chatOnly == "True" or chatOnly == "true":
            if requestedChannel.chatEnabled:
                hideBar = False
                hideBarReq = request.args.get("hideBar")
                if hideBarReq == "True" or hideBarReq == "true":
                    hideBar = True

                guestUser = None
                if (
                    "guestUser" in request.args
                    and current_user.is_authenticated is False
                ):
                    guestUser = request.args.get("guestUser")

                    userQuery = Sec.User.query.filter_by(username=guestUser).first()
                    if userQuery is not None:
                        flash("Invalid User", "error")
                        return redirect(url_for("root.main_page"))

                streamName = streamData.with_entities(
                    Stream.Stream.streamName
                ).scalar()

                return render_template(
                    themes.checkOverride("chatpopout.html"),
                    streamName=streamName,
                    sysSettings=sysSettings,
                    channel=requestedChannel,
                    hideBar=hideBar,
                    guestUser=guestUser,
                    stickerList=stickerList,
                    stickerSelectorList=stickerSelectorList,
                    bannedWords=[bw.word for bw in bwQuery.all()],
                    bannedMessages=[bm.msgID for bm in channelBmQuery.all()],
                    chatDomain = defaultChatDomain
                )
            else:
                flash("Chat is Not Enabled For This Stream", "error")

        # Stream URL Generation
        streamType = 'live'
        if sysSettings.proxyFQDN is not None:
            streamType = 'proxy'
        elif settings.edgeStreamer.query.filter_by(active=True).with_entities(settings.edgeStreamer.id).first() is not None:
            streamType = 'edge'

        streamURL = f"/{streamType}/{requestedChannel.channelLoc}/index.m3u8"
        if sysSettings.adaptiveStreaming is True:
            streamURL = f"/{streamType}-adapt/{requestedChannel.channelLoc}.m3u8"

        isEmbedded = request.args.get("embedded")

        if isEmbedded is None or isEmbedded == "False" or isEmbedded == "false":

            secureHash = None
            rtmpURI = None

            endpoint = "live"

            if requestedChannel.protected:
                if current_user.is_authenticated:
                    secureHash = None
                    if current_user.authType == 0:
                        secureHash = hashlib.sha256(
                            (
                                current_user.username
                                + requestedChannel.channelLoc
                                + current_user.password
                            ).encode("utf-8")
                        ).hexdigest()
                    else:
                        secureHash = hashlib.sha256(
                            (
                                current_user.username
                                + requestedChannel.channelLoc
                                + current_user.oAuthID
                            ).encode("utf-8")
                        ).hexdigest()
                    username = current_user.username
                    rtmpURI = (
                        "rtmp://"
                        + sysSettings.siteAddress
                        + ":1935/"
                        + endpoint
                        + "/"
                        + requestedChannel.channelLoc
                        + "?username="
                        + username
                        + "&hash="
                        + secureHash
                    )
                else:
                    # TODO Add method for Unauthenticated Guest Users with an invite code to view RTMP
                    rtmpURI = (
                        "rtmp://"
                        + sysSettings.siteAddress
                        + ":1935/"
                        + endpoint
                        + "/"
                        + requestedChannel.channelLoc
                    )
            else:
                rtmpURI = (
                    "rtmp://"
                    + sysSettings.siteAddress
                    + ":1935/"
                    + endpoint
                    + "/"
                    + requestedChannel.channelLoc
                )

            clipsList = cachedDbCalls.getAllClipsForChannel_View(requestedChannel.id)
            # for vid in requestedChannel.recordedVideo:
            #    for clip in vid.clips:
            #        if clip.published is True:
            #            clipsList.append(clip)
            clipsList.sort(key=lambda x: x.views, reverse=True)

            videoList = cachedDbCalls.getAllVideo_View(requestedChannel.id)
            videoList.sort(key=lambda x: x.views, reverse=True)

            subState = False
            if current_user.is_authenticated:
                chanSubQuery = subscriptions.channelSubs.query.filter_by(
                    channelID=requestedChannel.id, userID=current_user.id
                ).first()
                if chanSubQuery is not None:
                    subState = True

            channelPanelList = panel.panelMapping.query.filter_by(
                pageName="liveview.view_page",
                panelType=2,
                panelLocationId=requestedChannel.id,
            ).all()
            channelPanelListSorted = sorted(
                channelPanelList, key=lambda x: x.panelOrder
            )

            return render_template(
                themes.checkOverride("channelplayer.html"),
                stream=streamData.first(),
                streamURL=streamURL,
                topics=cachedDbCalls.getAllTopics(),
                channel=requestedChannel,
                clipsList=clipsList,
                videoList=videoList,
                subState=subState,
                secureHash=secureHash,
                rtmpURI=rtmpURI,
                stickerList=stickerList,
                stickerSelectorList=stickerSelectorList,
                bannedWords=[bw.word for bw in bwQuery.all()],
                bannedMessages=[bm.msgID for bm in channelBmQuery.all()],
                channelPanelList=channelPanelListSorted,
                chatDomain=defaultChatDomain
            )
        else:
            isAutoPlay = request.args.get("autoplay")
            if isAutoPlay is None:
                isAutoPlay = False
            elif isAutoPlay.lower() == "true":
                isAutoPlay = True
            else:
                isAutoPlay = False

            countViewers = request.args.get("countViewers")
            if countViewers is None:
                countViewers = True
            elif countViewers.lower() == "false":
                countViewers = False
            else:
                countViewers = False
            return render_template(
                themes.checkOverride("channelplayer_embed.html"),
                channel=requestedChannel,
                streamURL=streamURL,
                isAutoPlay=isAutoPlay,
                countViewers=countViewers,
                chatDomain=defaultChatDomain
            )

    else:
        flash("No Live Stream at URL", "error")
        return redirect(url_for("root.main_page"))
