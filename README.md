# Public releases

複数アプリの配布バイナリと最新版情報を置くリポジトリです。ソースコード、秘密鍵、認証情報、端末設定は置きません。バイナリも誰でも取得できるため、個人データや開発用の認証情報を含めないでください。

## 置き方

- `apps/<bundle-id>/stable.json`: そのアプリの最新版を指す小さな JSON（64 KiB 以下）。
- GitHub Releases のタグ `<bundle-id>-<version>-<build>`: 版ごとの ZIP と、その版の `stable.json` を添付します。GitHub 全体の `releases/latest` はアプリ間で競合するため使いません。
- `<bundle-id>` はアプリの `CFBundleIdentifier`。別アプリは別フォルダ・別タグを使い、同じアプリの複数CPU向け配布は1つの universal binary にまとめます。
- `stable` は本番用です。Preview / Staging / iOS の配布には使いません。iOS は TestFlight / App Store を使用します。

例（サイズ・ハッシュ・版は説明用です。実際のファイルから生成してください）:

```json
{
  "schemaVersion": 1,
  "appID": "local.masaki.DevBoard",
  "channel": "stable",
  "version": "0.43.0",
  "build": 12345,
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "notes": ["クラウドから最新版を受け取れます"],
  "minimumSystemVersion": "15.0",
  "architectures": ["arm64"],
  "asset": {
    "url": "https://github.com/ymasaki/public-releases/releases/download/local.masaki.DevBoard-0.43.0-12345/local.masaki.DevBoard-0.43.0-12345.zip",
    "size": 12345678,
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
```

`version` は表示用の `MAJOR.MINOR.PATCH`、`build` はアプリごとに単調増加する正整数（`CFBundleVersion` と一致）です。`commit` は署名された Info.plist の `DevBoardCommit` にも埋める40桁のソースリビジョンです。他のアプリもこのキーを配布ビルドに用意します。`notes` は1項目2000文字以内・最大100項目。`size` は ZIP の実バイト数、`sha256` は ZIP 全体の小文字64桁 SHA-256。`minimumSystemVersion` と `architectures` は起動前の互換性確認用で、署名されたバイナリとも照合します。

ZIP の直下は `<アプリ名>.app/` だけにします。実行権限を保持し、リンク・親ディレクトリ参照・重複項目を含めません。ZIP は512 MiB以下、展開後2 GiB以下、2万項目以下。フレームワーク等にシンボリックリンクがあるアプリは、この形式の利用前に各アプリ側で検討してください。

## 配布物を作る

1. 配布する版を人が決定します。署名前に Info.plist から開発端末のパス `DevBoardSourceRepo` を削除します（署名後には変更しません）。Developer ID Application でアプリと入れ子の実行物を署名し、必要な権限と hardened runtime を設定します。Apple Development / ad hoc 署名のビルドは一般配布しません。iCloud 等を利用する場合は配布用プロファイルも用意します。
2. Apple の `notarytool` で公証し、`xcrun stapler staple <app>` でチケットを付けます。Gatekeeper と `stapler validate` を通ることを確認します。署名・公証に使う資格情報はこのリポジトリへ保存しません。
3. このリポジトリの `python3 tools/prepare-release.py <署名・公証済みapp> <新しい出力フォルダ> --notes <変更点のUTF-8ファイル>`（DevBoard ソースでは `scripts/prepare-public-release.py`） を実行すると、署名・公証・構成を確認して ZIP と JSON をローカルに作ります。出力先の上書きやアップロードは行いません。他のアプリでも同じフィールドを生成してください。

## 公開する（人の操作）

公開はアプリごとに1人ずつ行います。人が本番公開を選んでから進め、エージェントが自動で公開する入口を作りません。

1. `apps/<bundle-id>/stable.json` の現在の `build` を確認し、新版のほうが大きいことを確認します。同じbuildを再利用しません。
2. 版別タグの Release を **draft** として作り、ZIP とその版の JSON を添付します。Release のタグ・ファイル名・JSON 内 URL が一致することを確かめます。
3. 人が Release を公開し、匿名で ZIP と JSON を取得してサイズ・SHA256を照合します。署名・公証・対象CPU・最低OSも確認します。
4. 最後に `apps/<bundle-id>/stable.json` を新しい JSON に更新します。直前に main を取得し直し、現行buildより大きいことを再確認します。GitHub Contents API を使う場合も、読み取った現行ファイルの SHA を指定した更新だけを使い、競合したら再読込・build比較をしてから判断します。先行する別の公開作業を上書きして巻き戻さないでください。

公開済み ZIP と版別 JSON は同じ URL で差し替えません。修正は新しいbuildで公開します。途中で失敗したら従来の stable を維持してください。古い Release は既存端末が参照する可能性があるため保持します。緊急で旧実装に戻す場合も、修正・復元した内容を**新しいbuildとして再署名・公証**して配布し、buildを後退させません。

## アプリ側の更新手順

アプリは `https://raw.githubusercontent.com/ymasaki/public-releases/main/apps/<bundle-id>/stable.json` を匿名で読みます。起動時、15分周期、利用者の手動確認を基本とし、他アプリのフォルダや GitHub の最新Release APIは使いません。HTTP キャッシュがあるため、公開直後の即時反映は保証しません。

1. スキーマ・appID・channel・容量・URL・対応OS/CPUを確かめ、自分と準備済み候補より大きいbuildだけを選びます。同buildで異なる内容が届いたら既存候補を維持します。
2. メタ情報は実受信64 KiB/全体30秒、ZIPは宣言size以下かつ512 MiB/全体10分、無通信30秒以内で取得します。HTTPSの指定repoの Release URL と GitHub 配布ホスト以外へ転送しません。資格情報は不要です。失敗・取消で取得枠と一時ファイルを解放します。
3. サイズ・SHA256・ZIPの項目/展開サイズを検査し、展開したアプリの Apple 署名、インストール済みアプリと同じ Team ID / Bundle ID、署名済み情報のbuild/version/commit、実行ファイルのCPU/OS互換を確かめます。メタ情報やSHA256だけを根拠に実行しません。各アプリは自身に合う検証器を実装します（DevBoardの検証器はDevBoard専用）。
4. 準備できたらアプリ内で知らせ、利用者が「アップデートを実行」を押した時に再検証して交換・再起動します。作業や入力画面の終了を待ち、起動失敗時には旧版へ戻せるようにします。

DevBoard は既存のホスト経由・ローカルビルドも残します。同時に複数の経路で取得・交換せず、開始した経路と候補を完了・失敗時も照合します。取得失敗で準備済み版を消しません。失敗した同じクラウド版は定期的に受け取り直さず、「アップデートを確認」で再試行します。iPhone自身の更新はTestFlightのままです。

参照: [GitHub Releases の管理](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)、[Apple の公証手順](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)。
