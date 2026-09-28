// MuProxy — man-in-the-middle giữa client MuMain và server OpenMU.
//
// Vì sao cần: traffic tới game server được mã hoá SimpleModulus + Xor32
// (xem MuMain/src/source/Network/Server/WSclient.cpp:356 — client bật mã hoá
// cho mọi port NGOÀI dải 0xAD00..0xADFF). tcpdump chỉ thấy rác. Proxy này
// giải mã bằng chính code của OpenMU nên không phải tự implement lại crypto.
//
// Luồng:
//   client --(plaintext)--> :44305 proxy --> :44405 connect server
//                           ^ rewrite gói C1 F4 03 (ConnectionInfo) để client
//                             quay về proxy thay vì đi thẳng game server
//   client --(encrypted)--> :56901 proxy --> :55901 game server
//
// Output: JSON Lines, mỗi dòng một packet đã giải mã.

using System.Buffers;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using MUnique.OpenMU.Network;
using MUnique.OpenMU.Network.SimpleModulus;
using MUnique.OpenMU.Network.Xor;
using Pipelines.Sockets.Unofficial;

var cfg = ParseArgs(args);

var loggerFactory = LoggerFactory.Create(b => b.SetMinimumLevel(LogLevel.Warning));
var started = DateTime.UtcNow;
var outLock = new object();
using var jsonl = new StreamWriter(cfg.Out, append: false) { AutoFlush = true };

void Emit(string channel, string dir, ReadOnlySpan<byte> data, string? note = null)
{
    var rec = new Dictionary<string, object?>
    {
        ["ms"] = Math.Round((DateTime.UtcNow - started).TotalMilliseconds, 1),
        ["ch"] = channel,
        ["dir"] = dir,                       // c2s | s2c
        ["len"] = data.Length,
        ["hex"] = Convert.ToHexString(data),
    };
    if (note is not null)
    {
        rec["note"] = note;
    }

    var line = JsonSerializer.Serialize(rec);
    lock (outLock)
    {
        jsonl.WriteLine(line);
    }

    Console.WriteLine($"{rec["ms"],9} {channel,-2} {dir} len={data.Length,-5} {Short(data)}{(note is null ? string.Empty : "  << " + note)}");
}

static string Short(ReadOnlySpan<byte> d)
{
    var n = Math.Min(d.Length, 24);
    var s = Convert.ToHexString(d[..n]);
    var sb = new StringBuilder();
    for (var i = 0; i < s.Length; i += 2)
    {
        sb.Append(s[i]).Append(s[i + 1]).Append(' ');
    }

    return sb.ToString().TrimEnd() + (d.Length > n ? " …" : string.Empty);
}

// ---------------------------------------------------------------- connect server
// Không mã hoá cả hai chiều: truyền null cho decryptor/encryptor creator.
var csListener = new Listener(cfg.CsListen, _ => null, _ => null, loggerFactory);
csListener.ClientAccepted += e => BridgeAsync(
    e.AcceptedConnection,
    cfg.CsTargetHost,
    cfg.CsTargetPort,
    channel: "CS",
    encryptedUpstream: false,
    rewriteConnectionInfo: true);
csListener.Start();

// ------------------------------------------------------------------- game server
// Proxy đóng vai server với client: giải mã chiều client->server, mã hoá chiều
// server->client. PipelinedDecryptor/PipelinedEncryptor là composite sẵn có của
// OpenMU (SimpleModulus + Xor32, khoá mặc định) — đúng bộ mà MuMain dùng.
var gsListener = new Listener(
    cfg.GsListen,
    reader => new PipelinedDecryptor(reader),
    writer => new PipelinedEncryptor(writer),
    loggerFactory);
gsListener.ClientAccepted += e => BridgeAsync(
    e.AcceptedConnection,
    cfg.GsTargetHost,
    cfg.GsTargetPort,
    channel: "GS",
    encryptedUpstream: true,
    rewriteConnectionInfo: false);
gsListener.Start();

Console.Error.WriteLine($"connect server proxy : 0.0.0.0:{cfg.CsListen}  ->  {cfg.CsTargetHost}:{cfg.CsTargetPort}   (plaintext)");
Console.Error.WriteLine($"game server proxy    : 0.0.0.0:{cfg.GsListen}  ->  {cfg.GsTargetHost}:{cfg.GsTargetPort}   (SimpleModulus+Xor32)");
Console.Error.WriteLine($"output               : {cfg.Out}");
Console.Error.WriteLine($"chay client          : ./Main /u127.0.0.1 /p{cfg.CsListen}");

await Task.Delay(Timeout.Infinite).ConfigureAwait(false);

// Nối một client đã được accept sang server thật, log cả hai chiều.
async ValueTask BridgeAsync(IConnection client, string host, int port, string channel, bool encryptedUpstream, bool rewriteConnectionInfo)
{
    try
    {
        var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        await socket.ConnectAsync(host, port).ConfigureAwait(false);
        var pipe = SocketConnection.Create(socket);

        // Proxy đóng vai CLIENT với server thật -> dùng đúng cặp khoá client,
        // giống MuMain/ClientLibrary/ConnectionManager.cs:162-163.
        var upDecryptor = encryptedUpstream
            ? new PipelinedSimpleModulusDecryptor(pipe.Input, PipelinedSimpleModulusDecryptor.DefaultClientKey)
            : null;
        var upEncryptor = encryptedUpstream
            ? new PipelinedXor32Encryptor(new PipelinedSimpleModulusEncryptor(pipe.Output, PipelinedSimpleModulusEncryptor.DefaultClientKey).Writer)
            : (IPipelinedEncryptor?)null;

        var server = new Connection(pipe, upDecryptor, upEncryptor, loggerFactory.CreateLogger<Connection>());

        var sendLock = new SemaphoreSlim(1, 1);

        async ValueTask ToServerAsync(byte[] data, string? note)
        {
            await sendLock.WaitAsync().ConfigureAwait(false);
            try
            {
                Emit(channel, "c2s", data, note);
                server.Output.Write(data);
                await server.Output.FlushAsync().ConfigureAwait(false);
            }
            finally
            {
                sendLock.Release();
            }
        }

        client.PacketReceived += async seq =>
        {
            var data = seq.ToArray();
            await ToServerAsync(data, null).ConfigureAwait(false);

            // --speedhack N: nhân bản WalkRequest thành N gói liên tiếp, mỗi gói
            // dịch điểm xuất phát thêm 4 ô về phía đông. Mô phỏng đúng thứ
            // SpeedHackDetectPlugIn.WalkCheatCheckAsync theo dõi: khoảng cách
            // Chebyshev giữa các điểm xuất phát liên tiếp so với thời gian trôi qua.
            if (cfg.SpeedHack > 0 && channel == "GS" && data.Length >= 6 && data[0] == 0xC1 && data[2] == 0xD4)
            {
                for (var i = 1; i <= cfg.SpeedHack; i++)
                {
                    await Task.Delay(20).ConfigureAwait(false);
                    var fake = (byte[])data.Clone();
                    fake[3] = (byte)(fake[3] + (4 * i));      // SourceX dịch dần
                    await ToServerAsync(fake, $"INJECT speedhack #{i} (SourceX {data[3]} -> {fake[3]})").ConfigureAwait(false);
                }
            }
        };

        server.PacketReceived += async seq =>
        {
            var data = seq.ToArray();
            string? note = null;

            if (rewriteConnectionInfo && IsConnectionInfo(data))
            {
                var (origHost, origPort) = ReadConnectionInfo(data);
                WriteConnectionInfo(data, "127.0.0.1", cfg.GsListen);
                note = $"rewrite ConnectionInfo {origHost}:{origPort} -> 127.0.0.1:{cfg.GsListen}";

                // Nối thẳng proxy game server tới đúng endpoint client được cấp.
                cfg.GsTargetHost = origHost;
                cfg.GsTargetPort = origPort;
            }

            Emit(channel, "s2c", data, note);
            client.Output.Write(data);
            await client.Output.FlushAsync().ConfigureAwait(false);
        };

        client.Disconnected += async () =>
        {
            Console.Error.WriteLine($"[{channel}] client ngat ket noi");
            await server.DisconnectAsync().ConfigureAwait(false);
        };
        server.Disconnected += async () =>
        {
            Console.Error.WriteLine($"[{channel}] server ngat ket noi");
            await client.DisconnectAsync().ConfigureAwait(false);
        };

        _ = client.BeginReceiveAsync();
        _ = server.BeginReceiveAsync();
        Console.Error.WriteLine($"[{channel}] bridge len: client <-> {host}:{port}");
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"[{channel}] khong noi duoc toi {host}:{port}: {ex.Message}");
        await client.DisconnectAsync().ConfigureAwait(false);
    }
}

// C1 16 F4 03 — ConnectionInfo (docs/Packets/C1-F4-03-ConnectionInfo_by-server.md)
//   index 4..19 : IpAddress (chuoi 16 byte, pad \0)
//   index 20..21: Port (short little endian)
static bool IsConnectionInfo(byte[] d) =>
    d.Length >= 22 && d[0] == 0xC1 && d[2] == 0xF4 && d[3] == 0x03;

static (string Host, int Port) ReadConnectionInfo(byte[] d)
{
    var host = Encoding.ASCII.GetString(d, 4, 16).TrimEnd('\0');
    var port = d[20] | (d[21] << 8);
    return (host, port);
}

static void WriteConnectionInfo(byte[] d, string host, int port)
{
    Array.Clear(d, 4, 16);
    Encoding.ASCII.GetBytes(host).CopyTo(d, 4);
    d[20] = (byte)(port & 0xFF);
    d[21] = (byte)((port >> 8) & 0xFF);
}

static Config ParseArgs(string[] a)
{
    var c = new Config();
    for (var i = 0; i + 1 < a.Length; i += 2)
    {
        switch (a[i])
        {
            case "--cs-listen": c.CsListen = int.Parse(a[i + 1]); break;
            case "--cs-target": (c.CsTargetHost, c.CsTargetPort) = Split(a[i + 1]); break;
            case "--gs-listen": c.GsListen = int.Parse(a[i + 1]); break;
            case "--gs-target": (c.GsTargetHost, c.GsTargetPort) = Split(a[i + 1]); break;
            case "--out": c.Out = a[i + 1]; break;
            case "--speedhack": c.SpeedHack = int.Parse(a[i + 1]); break;
        }
    }

    return c;

    static (string, int) Split(string s)
    {
        var p = s.Split(':');
        return (p[0], int.Parse(p[1]));
    }
}

internal sealed class Config
{
    // 44305 = 0xAD11, nam TRONG dai 0xAD00..0xADFF -> client coi la connect
    // server va KHONG ma hoa. Doi ra ngoai dai la client se ma hoa -> hong.
    public int CsListen { get; set; } = 44305;

    public string CsTargetHost { get; set; } = "127.0.0.1";

    public int CsTargetPort { get; set; } = 44405;

    // 56901 nam NGOAI dai tren -> client ma hoa, dung nhu game server that.
    public int GsListen { get; set; } = 56901;

    public string GsTargetHost { get; set; } = "127.0.0.1";

    public int GsTargetPort { get; set; } = 55901;

    public string Out { get; set; } = "/tmp/mu-packets.jsonl";

    // >0: bat che do inject de THU cơ che chong speedhack cua server.
    public int SpeedHack { get; set; }
}
