# Configuration and registry reference

> 来源：OpenGlass 官方文档快照（<https://github.com/ALTaleX531/OpenGlass>），
> 内容与版权归原作者，此处仅作离线参考。

> [!NOTE]
> These instructions apply to upcoming OpenGlass v3.1.0. In earlier v3 releases, GUI controls and storage behavior differ.

## Editing scope and read order

| Choice | What it does | When to choose |
| --- | --- | --- |
| Shared (`HKLM`) | The default GUI view. Sets shared computer defaults for uncustomized settings. | Recommended for most single-user setups when not using the [theme extension](Windows-theme-integration) or related Windhawk mods that customize per-user theme, color, or glass settings. |
| Personal (`HKCU`) | Limited to your personal account. Ordinary personal settings take priority over shared defaults. | Preferable for multiple accounts with separate appearances, Windows-style per-user theme behavior, or coordinating GUI edits with the theme extension or related Windhawk mods that write personal settings. |

Both views require administrator permission, but entering credentials for another administrator does not change whose personal settings are edited.

Windows accent color and transparency normally affect your own Windows account in either view (see [Colorization settings](#colorization-settings)).

### Switching views

1. Save or Revert pending changes, and wait for active symbol downloads to finish.
2. Hold **Shift** while clicking **More** in the bottom-left corner.
3. Choose **Switch to HKCU view** or **Switch to HKLM view**.

Switching views changes the editing destination without copying or moving stored values. Changes are written while editing. **Save** keeps them, and **Revert** or normal window close undoes pending changes.

### How inheritance works

For ordinary settings, OpenGlass uses the first valid value in HKCU, then HKLM, or otherwise falls back to the built-in default. Missing values and invalid registry types are skipped in both hives. Controls display the selected view's value or default, which may differ from what OpenGlass actually uses.

## Restore defaults

To reset settings, click **More** in the bottom-left corner and choose **Restore defaults...**. This clears all known OpenGlass customizations in the selected layer while preserving the other layer, Windows base colors, Windows transparency, unknown settings, and diagnostic settings. Resetting the personal HKCU view removes personal customizations so shared defaults apply. Restoring defaults starts an immediate preview: click **Save** to keep the reset, or click **Revert** to restore your previous settings.

## Optional merge

Merging is optional and unnecessary for multi-user use.

Save or revert any pending edits before starting. Switch to the destination view you want, click **More** in the bottom-left corner, and choose **Merge into HKCU...** or **Merge into HKLM...**:

- **Merge into HKLM:** Available in HKLM view. Copies ordinary settings currently in use into shared defaults and removes the corresponding valid personal values from your account. It never touches other user accounts, but changing shared defaults can affect their appearance if they rely on those defaults.
- **Merge into HKCU:** Available in HKCU view. Copies ordinary settings currently in use into your personal settings and preserves shared defaults.

After you review and confirm the merge, OpenGlass starts a reversible preview. Click **Save** to keep the merged settings, or click **Revert** to undo them.

## Colorization settings

The transparency checkbox and color palette are on the **Glass colors** tab.

### Transparency

The **Enable transparency** checkbox controls Windows transparency for your account in either view. If the Windows setting is missing or invalid, the checkbox appears off. Clicking **Save** keeps your changes, while **Revert** restores the previous state, restoring off if the setting was originally absent. OpenGlass never deletes the Windows setting.

If you launch the GUI with `OpenGlassGUI.exe --no-system-transparency`, the checkbox instead controls OpenGlass transparency settings directly in your chosen view.

### Palette and intensity

The palette shows color swatches with names underneath. Click a color, or press **Enter** or **Space** to select it. For **Custom**, activating it once selects its current color. Activating it a second time with Enter or Space, or double-clicking it, opens the color dialog. Canceling the dialog makes no further change. Arrow keys, Home, and End move focus through the palette without selecting colors.

The color intensity slider ranges from 10% to 85% in the chosen view. In Windows 7 glass mode, click **Composition parameters** to expand the section, which starts collapsed. It provides Color balance, Afterglow balance, and Blur balance sliders ranging from 0 to 100 (defaults 10, 10, and 50) for the chosen view only. Adjusting these balance sliders manually does not change your color mode, intensity slider position, or the other view. Changing intensity, transparency, or color selections recalculates balance values automatically. Vista mode hides the composition parameters section without deleting its stored values. Selecting a color does not reset reflection, inactive glass, or advanced blending settings.

### Windows color interactions

The GUI manages Windows accent colors for your user account across both views:

- **Manual:** Selecting a fixed or custom color disables Windows Automatic coloring and updates your accent color.
- **Automatic:** Enables Windows automatic accent mode to use a wallpaper-derived color, unless a Windows color policy substitutes a policy color during selection or recovery. Windows Explorer must be running to select and recover Automatic mode, including when leaving it. Choosing Automatic updates intensity and, in Windows 7 glass mode, also recalculates balance overrides. Later wallpaper changes retain that strength, while applying a preset uses the preset's saved strength.
- **Save and Revert:** **Save** synchronizes your Windows menu accent preference when the Windows glass color is available. Your settings still save if that color is missing. **Revert** restores each Manual color to its original value or absence. If you started from Automatic, it recomputes the current wallpaper color.

Choosing a fixed, custom, or Automatic color, or applying a preset, clears both `ColorizationColorOverride` and `ColorizationAfterglowOverride` from your own HKCU and shared HKLM, even while in personal view. Other user accounts are not touched. Balance overrides continue to control glass strength, but their values may change when a color or preset is applied.

## Accent compatibility

The **Override accent** setting replaces eligible Accent blur and acrylic surfaces with OpenGlass effects on both renderers, without altering Windows accent RGB. It does not replace independently composed application backdrops or affect client blur. On the **System** tab, the **Compatibility mitigations** section contains the checkbox **Limit accent override to supported shell windows**, enabled by default. This permits taskbars, tagged Start menus, supported jump lists, taskbar thumbnails, and notification overflow, while leaving ordinary menus and drop-downs on native effects.

Clearing the checkbox allows other eligible Accent windows to use OpenGlass effects, though applications can opt out individually. Developers can configure window properties directly as described in [How OpenGlass renders glass](How-OpenGlass-renders-glass#application-window-properties). Changing this mitigation does not enable Override accent by itself.

## Registry reference

Settings can be edited manually in the Windows Registry while OpenGlass is running or stopped. External registry edits do not reload automatically. Glass and color settings reload on a Windows color notification, while `CaptionButtons`, `TextGlowMode`, button-glow part IDs, and resource paths require a theme notification. Restarting OpenGlass reloads all settings and is mandatory for startup-only changes. GUI edits notify automatically. Storing an explicit numeric default remains a customization rather than an inherited or absent setting.

By default, the transparency checkbox manages `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize\EnableTransparency` (DWORD `0` or `1`). When launched with `--no-system-transparency`, the checkbox instead toggles `ColorizationOpaqueBlend` directly in the active view, deleting the value when checked and writing DWORD `1` when unchecked.

### Editing controls

The window title shows `(HKCU: username)` or `(HKLM)` to indicate the active editing view. `HKCU` corresponds to `HKEY_CURRENT_USER` and `HKLM` corresponds to `HKEY_LOCAL_MACHINE`.

You can also launch the GUI directly into a specific view from the command line:

- `OpenGlassGUI.exe --scope=hkcu` (edits personal settings)
- `OpenGlassGUI.exe --scope=hklm` (edits shared defaults)

To refresh settings displayed in the GUI after changing them externally, save or revert any pending GUI edits first. Then hold **Shift**, click **More**, and choose **Sync**. Sync refreshes the displayed settings, but it does not make manual registry changes take effect. External changes still follow the [Registry reference](#registry-reference) reload instructions above.

Two icons explain the relationship between views:

- A **yellow warning icon** in HKLM view means your personal value takes priority over this shared machine value.
- An **information icon** in HKCU view indicates that no personal customization is set, so the shared machine setting is inherited.

### Runtime lookup order

Runtime lookup is independent of the editing view. Both views use `SOFTWARE\Microsoft\Windows\DWM`:

| Property | Lookup order |
| --- | --- |
| Ordinary setting | HKCU → HKLM → built-in default |
| Overridable colorization setting | HKCU Override → HKLM Override → HKCU base → HKLM base → built-in default |

Invalid types are skipped. Both `Legacy` and `MILComp` use this order. While ordinary settings follow personal-over-shared precedence, overridable color settings prioritize explicit machine `Override` values over personal base colors. Resource strings for `CustomThemeReflection`, `CustomThemeMaterial`, and `CustomThemeAtlas` require absolute paths to existing local PNG files. Relative and network paths are rejected. `REG_SZ` and `REG_EXPAND_SZ` are accepted, but environment variables are not expanded.

[Presets](Preset-packages) capture effective configuration across both views. For ordinary settings, applying a preset writes values to the active view: applying to HKLM removes only the current user's conflicting covered values (harmless identical values remain), applying to HKCU leaves HKLM ordinary settings intact, and Default removes the target view only and can inherit. Windows color and transparency exceptions are handled separately (see [Colorization settings](#colorization-settings)).

### Colorization values

`ColorizationColorCaption`, `ColorizationOpacity`, and `ColorizationGlassReflectionOpacity` support state variants with suffixes `Inactive`, `Maximized`, and `InactiveMaximized`. Each full key is resolved through HKCU and HKLM first. When a variant has no valid value in either layer, `Inactive` and `Maximized` fall back to the unsuffixed base setting, and `InactiveMaximized` falls back to `Inactive`. An inherited Auto or theme choice is evaluated for each state instead of copying the active window appearance.

For GUI management rules and schema handling for colorization and balance values, see the [Configuration design contract](https://github.com/ALTaleX531/OpenGlass/blob/main/OpenGlassGUI/Configuration.design.md#managed-settings-and-color-destinations).

| Value name | Type | Description |
| --- | --- | --- |
| `ColorizationColor(Override)`<br>`ColorizationColorInactive`<br>`ColorizationAfterglow(Override)` | DWORD | ARGB glass color (alpha is ignored). The `Inactive` color is used by Vista glass, and afterglow by Windows 7 glass. `ColorizationColorInactive` inherits the selected main color when not set, including any active `Override` precedence. |
| `ColorizationColorBalance(Override)`<br>`ColorizationAfterglowBalance(Override)`<br>`ColorizationBlurBalance(Override)` | DWORD | Windows 7 Aero composition parameters. Values are clamped to 0-100, with runtime fallback 0 when all candidates are absent or invalid. |
| `GlassOpacity`<br>`GlassOpacityInactive` | DWORD | Vista glass color intensity from 0-100% (default 63%). `GlassOpacityInactive` inherits `GlassOpacity` when not set. The GUI also stores the Windows 7 intensity slider in `GlassOpacity`, while Windows 7 rendering uses the three balance values. |
| `ColorizationColorCaption` and its state variants | DWORD | Caption color in `0xBBGGRR`. `0xFFFFFFFD` is default OpenGlass Auto, choosing black or white text depending on window state and glass mode. `0xFFFFFFFF` lets Windows determine text color, and `0xFFFFFFFE` reads theme `TEXTCOLOR`. |
| `ColorizationOpaqueBlend` | DWORD | Controls whether the glass effect is opaque (default 0). |
| `ColorizationBaseTransparent`<br>`ColorizationBaseMaximized`<br>`ColorizationBaseOpaque` | DWORD | ARGB blend base. `0xFFFFFFFE` is default Auto and `0xFFFFFFFF` reads theme `COLORIZATIONCOLOR`. |
| `ColorizationOpaqueBlendPriority` | DWORD | When opaque and maximized simultaneously, `0` prioritizes `ColorizationBaseMaximized` (Vista) and `1` prioritizes `ColorizationBaseOpaque` (Win7). Default `0xFFFFFFFF` selects the rule from `GlassType`. |
| `ColorizationOpacity` and its state variants | DWORD | Additional 0-100% glass blending factors. `0xFFFFFFFE` is default Auto and `0xFFFFFFFF` reads theme `COLORIZATIONOPACITY`. |

### Glass settings

| Value name | Type | Description |
| --- | --- | --- |
| `GlassType` | DWORD | `0` for Windows Vista glass (default), `1` for Windows 7 glass. |
| `GlassOverrideAccent` | DWORD | Replaces eligible accent-blur and acrylic surfaces with OpenGlass effects on both renderers (default 0). Window eligibility is governed by [Accent compatibility](#accent-compatibility). Does not set Windows accent color or replace independently composed application backdrops. |
| `CustomThemeReflection` | String | Reflection texture stretched over the desktop and rendered above glass. |
| `ColorizationGlassReflectionIntensity` | DWORD | Window-frame reflection strength from 0–100% (default 0). Aero Peek reflections on both renderers and Legacy Aero Snap reflections are controlled by policy bits and are not disabled by setting intensity to 0. |
| `ColorizationGlassReflectionOpacity` and its state variants | DWORD | Window-frame base reflection opacity from 0–100%. `0xFFFFFFFE` is default Auto and `0xFFFFFFFF` reads theme reflection opacity. |
| `ColorizationGlassReflectionParallaxIntensity` | DWORD | Window-frame reflection parallax from 0–100% (default 13%). At 0% the reflection is screen-anchored, and at 100% it follows the window horizontally. |
| `ColorizationGlassReflectionPolicy` | DWORD | Reflection targets: window frame `1<<0`, Aero Peek on both renderers `1<<2`, Legacy Aero Snap `1<<3`, or `0xFFFFFFFF` everywhere available (default). |
| `BlurDeviation` | DWORD | Historical encoding of the blur amount for the non-D3D renderer: `BlurAmount = min(BlurDeviation × 0.3, 250)`. Default 30 gives amount 9, and 0 disables blur. The GUI shows a rounded amount from 0–30 and writes the corresponding encoding. |
| `BlurOptimization` | DWORD | Non-D3D blur optimization: `0` speed (default), `1` balance, `2` quality. |
| `RoundRectRadius` | DWORD | Glass geometry radius (default 0, Windows 7 style 6). |
| `CustomThemeMaterial` | String | Texture tiled above glass regions. |
| `MaterialOpacity` | DWORD | Material opacity from 0–100% (default 0%). |
| `UseDirect3DRendering` | DWORD | Set to 1 for the D3D11 renderer (default 0). It ignores `BlurDeviation` and `BlurOptimization` and uses a fixed Gaussian σ of 3 px. |

`BlurDeviation` keeps Glass8's registry convention. The GUI labels the decoded value **Blur amount** because it is not interchangeable with a Gaussian σ or radius. Sampling and occlusion margins are calculated separately.

In the non-Direct3D renderer, setting **Appearance** > **Blur amount** to 9 removes `BlurDeviation` from the selected editing view and allows inheritance. In contrast, other controls may keep explicitly stored default values rather than removing their saved settings.

### Theme settings

| Value name | Type | Description |
| --- | --- | --- |
| `CaptionButtons` | DWORD | Caption-button style: `0` vanilla, `1` Vista, `2` Windows 7, `3` Windows 8. |
| `MINMAXBUTTONGLOWid`<br>`CLOSEBUTTONGLOWid`<br>`TOOLCLOSEBUTTONGLOWid` | DWORD | Atlas part IDs for normal, close and tool-close button glow on both renderers (defaults `93`, `92`, `94`). Reload the theme after editing. |
| `CenterCaption` | DWORD | `0` left, `1` centered, `2` Windows 8 centering. |
| `TextGlowMode` | DWORD | `0` none, `1` atlas glow, `2` atlas glow respecting theme opacity, `3` composited theme glow. Modes 1 and 2 must be exact values with no high-word size. Mode 3 uses the high word for glow size, where 0 uses theme `TEXTGLOWSIZE`. |
| `CustomThemeAtlas` | String | PNG theme atlas following the active msstyle layout by default. An optional layout mapping uses the complete PNG filename plus `.layout` (such as `atlas.png.layout`) to describe a different layout. |
| `DisableModernBorders` | DWORD | Set to 1 to disable Windows 11 modern rounded borders. |

On MILComp, `CaptionHeight` in the atlas `.layout` caps vanilla caption-button height using DWM's DPI scale. Explicit `CaptionButtons` styles (1 to 3) keep their own metrics.

MILComp also draws atlas button glows during hover and press, using native button fade and layout. Their appearance depends on the selected atlas.

For caption text glow, **Use theme atlas (opacity)** respects each theme and layout state's opacity, including zero. Automatic caption colors do not override this opacity. **Use theme atlas** ignores that opacity.

### Advanced settings

| Value name | Type | Description |
| --- | --- | --- |
| `DisableGlassOnBattery` | DWORD | Controls the response to Windows energy saver. `1` makes the rendered glass opaque while energy saver is active, and `0` leaves its normal transparency unchanged. Default: `1`. |
| `DisabledHooks` | DWORD | Disables handler hooks at startup: `0x1` CaptionTextHandler, `0x2` AccentOverrider, `0x4` GlassFrameHandler, `0x8` GlassReflectionHandler, `0x10` CaptionMetricsTweaker. Combine bits as needed (default `0` disables none). Changes require restarting OpenGlass. |
| `EnableUxMitigation` | DWORD | Compatibility bitmask (default `1`). Bit `0x1` limits Accent override to supported shell windows, and `0` clears the restriction. See [Accent compatibility](#accent-compatibility). GUI changes rebuild existing Accent effects, whereas manual registry edits require a Windows color notification or restart. Client blur is unaffected. |
| `GlassSafetyZoneMode` | DWORD | Controls the extra rendering area used to protect blurred glass from occlusion clipping. `0` disables it, `1` applies it when the tracked glass coverage is visible, and `2` applies it for every otherwise eligible visual-tree draw. Values above `2` are clamped to `2`. Default: `1`. |

Active Battery Saver or Energy Saver can make rendered glass opaque. See [diagnosing opaque glass](Troubleshooting-and-crash-dumps#diagnosing-opaque-glass) for diagnostic checks.
